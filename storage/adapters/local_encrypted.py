"""
本地加密 JSON 文件存储适配器

实现 storage/README.md 中定义的抽象接口，使用本地 JSON 文件存储持久化档案，并对所有用户数据进行加密存储。

当前运行模式：local_encrypted（加密的本地存储）

数据存储目录：storage/data/{user_id}/
- auth.json             密码验证信息（不加密）
- profile.json          生活风格画像（全量版，加密）
- profile.lite.json     生活风格画像（精简注入版，加密）
- config.json           用户配置（模块开关，加密）
- progress.json         当前探索进度（加密）
- insights/             洞察卡目录（加密）
- conversations/        对话记录目录（加密）
- patterns/             模式卡目录（加密）
- reviews/              回顾报告目录（加密）
- deleted/              已删除文件目录（加密）

加密方式：
- Fernet 对称加密（AES-128-CBC + HMAC-SHA256）
- 基于用户密码派生密钥（PBKDF2-HMAC-SHA256，100000 次迭代）
- 每个用户数据文件单独加密

复用经验来源：
- GitHub 上的密码管理器项目：使用 Fernet 对称加密、基于用户密码派生密钥（PBKDF2）、存储在 JSON 文件中
- know-yourself：全量版+精简注入版双档案设计、配置.json 模块开关、进度保存机制
- diarygpt：源—派生关系、检索前重验与删除失效（删除源记录时级联删除派生记录）
"""

import base64
import hmac
import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# 导入未加密存储适配器，继承其逻辑
import sys
sys.path.insert(0, str(Path(__file__).parent))
from local_json import LocalJsonStorageAdapter


class LocalEncryptedStorageAdapter(LocalJsonStorageAdapter):
    """本地加密 JSON 文件存储适配器"""

    # PBKDF2 迭代次数
    ITERATIONS = 100000
    # KDF 版本：
    #   v1 = PBKDF2-HMAC-SHA256 / ITERATIONS 轮，验证盐与 Fernet 密钥盐同源（单 salt），
    #        存在"读到 auth.json 即拿到密钥材料"的已知缺陷，仅用于读取旧档案。
    #   v2 = 同 PBKDF2 参数，但验证用 verify_salt、Fernet 密钥用 key_salt（两个独立随机盐，
    #        domain separation），读 auth.json 的人只有盐、没有密码，推不出密钥。新档案/改密一律 v2。
    # 旧档案无 kdf_version 时按 v1 兼容读取；改密后自动升级为 v2。
    KDF_VERSION = 2

    def __init__(
        self,
        base_dir: str = "storage/data",
        user_id: str = "default",
        password: Optional[str] = None,
    ):
        """
        初始化存储适配器

        Args:
            base_dir: 基础目录（默认 storage/data）
            user_id: 用户 ID（用于隔离不同用户的数据）
            password: 用户密码（用于派生加密密钥）
                     如果是首次使用，需要设置密码
                     如果是已有数据，需要提供正确的密码才能解密
        """
        self.base_dir = Path(base_dir)
        self.user_id = user_id
        self.user_dir = self.base_dir / user_id
        self._ensure_directories()

        self._password = password
        self._key = None
        self._fernet = None

        if password is not None:
            self._init_encryption(password)

    def _init_encryption(self, password: str):
        """
        初始化加密

        如果是首次使用，创建密码验证信息并派生密钥
        如果是已有数据，验证密码并派生密钥

        Args:
            password: 用户密码
        """
        auth_path = self.user_dir / "auth.json"

        if not auth_path.exists():
            # 首次使用（v2）：验证哈希与 Fernet 密钥使用两个独立随机盐，
            # 避免"读到 auth.json 的人直接拿到密钥"的同源派生缺陷。
            verify_salt = os.urandom(16)
            key_salt = os.urandom(16)
            password_hash = self._derive_bytes(password, verify_salt)

            auth_data = {
                "verify_salt": base64.b64encode(verify_salt).decode("utf-8"),
                "key_salt": base64.b64encode(key_salt).decode("utf-8"),
                "password_hash": base64.b64encode(password_hash).decode("utf-8"),
                "iterations": self.ITERATIONS,
                "kdf_version": 2,
                "algorithm": "PBKDF2-HMAC-SHA256",
                "created_at": self._now(),
            }

            # auth.json 不加密，但原子写入，避免中断留下损坏认证文件
            self._atomic_write_bytes(
                auth_path, json.dumps(auth_data, ensure_ascii=False, indent=2).encode("utf-8")
            )

            self._key = self._fernet_key_material(password, key_salt)
            self._fernet = Fernet(self._key)
        else:
            # 已有数据，验证密码并派生密钥
            with open(auth_path, "r", encoding="utf-8") as f:
                auth_data = json.load(f)

            iterations = auth_data.get("iterations", self.ITERATIONS)
            stored_hash = base64.b64decode(auth_data["password_hash"])

            if "key_salt" in auth_data or auth_data.get("kdf_version", 1) >= 2:
                # v2：验证用 verify_salt，Fernet 密钥用 key_salt（两个独立盐）
                verify_salt = base64.b64decode(auth_data["verify_salt"])
                key_salt = base64.b64decode(auth_data["key_salt"])
                password_hash = self._derive_bytes(password, verify_salt, iterations, 2)
                if not hmac.compare_digest(password_hash, stored_hash):
                    raise ValueError("密码错误，无法解密数据")
                self._key = self._fernet_key_material(password, key_salt, iterations, 2)
            else:
                # v1 兼容（旧档案：验证盐与密钥盐同源）——只读兼容，改密后自动升 v2
                salt = base64.b64decode(auth_data["salt"])
                password_hash = self._derive_bytes(password, salt, iterations, 1)
                if not hmac.compare_digest(password_hash, stored_hash):
                    raise ValueError("密码错误，无法解密数据")
                self._key = self._fernet_key_material(password, salt, iterations, 1)
            self._fernet = Fernet(self._key)

    def _derive_bytes(
        self, password: str, salt: bytes, iterations: int = None, kdf_version: int = 1
    ) -> bytes:
        """按 kdf_version 从密码派生 32 字节密钥材料。

        v1 与 v2 的 PBKDF2 参数完全相同（PBKDF2-HMAC-SHA256 / 32 字节）；
        区别不在算法，而在 salt：v1 验证与加密共用一个 salt，v2 用两个独立 salt
        （见调用处 verify_salt / key_salt）。因此两个版本走同一段派生代码。
        """
        if iterations is None:
            iterations = self.ITERATIONS
        if kdf_version in (1, 2):
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=iterations,
            )
            return kdf.derive(password.encode("utf-8"))
        # 未知版本：明确报错，而不是静默按旧参数派生（静默会导致数据永久锁死）
        raise ValueError(
            f"不支持的 kdf_version={kdf_version}（本程序支持 v1 读取兼容与 v2）。"
            f"这通常意味着档案由更新版本的程序生成，请升级本 Skill。"
        )

    def _derive_password_hash(
        self, password: str, verify_salt: bytes, iterations: int = None, kdf_version: int = 1
    ) -> bytes:
        """从密码派生密码验证哈希（使用 verify_salt，与 Fernet 密钥所用的 key_salt 不同）。"""
        return self._derive_bytes(password, verify_salt, iterations, kdf_version)

    def _fernet_key_material(
        self, password: str, key_salt: bytes, iterations: int = None, kdf_version: int = 1
    ) -> bytes:
        """从密码派生 Fernet 密钥（使用 key_salt）。返回 base64-url 编码的 32 字节密钥。"""
        raw = self._derive_bytes(password, key_salt, iterations, kdf_version)
        return base64.urlsafe_b64encode(raw)

    def verify_password(self, password: str) -> bool:
        """
        验证密码是否正确

        Args:
            password: 待验证的密码

        Returns:
            True 如果密码正确，False 否则
        """
        auth_path = self.user_dir / "auth.json"
        if not auth_path.exists():
            return False

        with open(auth_path, "r", encoding="utf-8") as f:
            auth_data = json.load(f)

        stored_hash = base64.b64decode(auth_data["password_hash"])
        iterations = auth_data.get("iterations", self.ITERATIONS)

        if "key_salt" in auth_data or auth_data.get("kdf_version", 1) >= 2:
            verify_salt = base64.b64decode(auth_data["verify_salt"])
            password_hash = self._derive_bytes(password, verify_salt, iterations, 2)
        else:
            verify_salt = base64.b64decode(auth_data["salt"])
            password_hash = self._derive_bytes(password, verify_salt, iterations, 1)
        # 常量时间比较，避免时序侧信道
        return hmac.compare_digest(password_hash, stored_hash)

    def change_password(self, old_password: str, new_password: str) -> bool:
        """
        修改密码（事务式：全解密验证 → 写临时副本 → 原子切换，不留备份）

        安全保证：
        1. 先用旧密码解密【全部】数据文件到内存；任一文件解密失败立即中止，
           不写任何文件，旧密码与全部旧密文保持原样（不再静默跳过文件，
           否则被跳过的文件在 auth 换新后将永远无法解密、等于静默丢数据）。
        2. 全部解密成功后，新密文先写到各自的 .rekey.tmp 临时文件，不覆盖原文件；
           任一写入失败即清理临时文件并中止，原文件与 auth.json 全不变。
        3. 临时副本全部就绪后，逐个 os.replace 原子替换数据文件，最后才原子写
           auth.json；auth.json 更新即代表改密正式提交。按项目决定不保留改密前副本。

        Args:
            old_password: 旧密码
            new_password: 新密码

        Returns:
            True 修改成功；旧密码错误返回 False
        Raises:
            RuntimeError: 有数据文件无法用旧密码解密（可能损坏），改密已中止、原档案不变
        """
        # 阶段0：验证旧密码
        if not self.verify_password(old_password):
            return False

        with open(self.user_dir / "auth.json", "r", encoding="utf-8") as f:
            old_auth = json.load(f)
        old_iter = old_auth.get("iterations", self.ITERATIONS)
        old_kdf = old_auth.get("kdf_version", 1)  # 旧档案按其记录的版本解密，缺省 v1
        # 兼容 v1/v2：v2 用 key_salt，v1 退化为单一 salt（验证盐与密钥盐同源）
        if "key_salt" in old_auth or old_kdf >= 2:
            old_key_salt = base64.b64decode(old_auth["key_salt"])
        else:
            old_key_salt = base64.b64decode(old_auth["salt"])
        old_fernet = Fernet(self._fernet_key_material(old_password, old_key_salt, old_iter, old_kdf))

        # 收集所有需要重新加密的数据文件（auth.json 不加密；排除临时文件）
        encrypted_files = []
        for root, _dirs, files in os.walk(self.user_dir):
            for name in files:
                if name == "auth.json" or not name.endswith(".json"):
                    continue
                if name.endswith(".tmp"):
                    continue
                encrypted_files.append(Path(root) / name)

        # 阶段1：用旧密码解密全部文件到内存。任一失败立即中止，磁盘一个字节都不改
        decrypted_data = {}
        for file_path in encrypted_files:
            with open(file_path, "rb") as f:
                encrypted_content = f.read()
            try:
                decrypted_data[file_path] = old_fernet.decrypt(encrypted_content)
            except InvalidToken as exc:
                raise RuntimeError(
                    f"文件 {file_path.name} 无法用旧密码解密，改密已中止，"
                    f"原密码与全部档案保持不变（该文件可能已损坏）。"
                ) from exc

        # 新密钥材料（一律升级到 v2：验证盐与密钥盐独立）
        new_verify_salt = os.urandom(16)
        new_key_salt = os.urandom(16)
        new_password_hash = self._derive_bytes(new_password, new_verify_salt)
        new_fernet = Fernet(self._fernet_key_material(new_password, new_key_salt))

        # 阶段2：新密文先全部写到临时文件，不覆盖任何原文件
        tmp_pairs = []
        try:
            for file_path, plaintext in decrypted_data.items():
                tmp_path = file_path.with_name(file_path.name + ".rekey.tmp")
                self._atomic_write_bytes(tmp_path, new_fernet.encrypt(plaintext))
                tmp_pairs.append((tmp_path, file_path))

            # 阶段3：临时副本全部就绪，逐个原子替换数据文件（同盘 rename，原子可靠）
            for tmp_path, target in tmp_pairs:
                os.replace(tmp_path, target)

            # 最后才原子更新 auth.json —— 它落盘代表改密正式提交（v2 双盐）
            new_auth = {
                "verify_salt": base64.b64encode(new_verify_salt).decode("utf-8"),
                "key_salt": base64.b64encode(new_key_salt).decode("utf-8"),
                "password_hash": base64.b64encode(new_password_hash).decode("utf-8"),
                "iterations": self.ITERATIONS,
                "kdf_version": 2,
                "algorithm": "PBKDF2-HMAC-SHA256",
                "created_at": self._now(),
            }
            self._atomic_write_bytes(
                self.user_dir / "auth.json",
                json.dumps(new_auth, ensure_ascii=False, indent=2).encode("utf-8"),
            )
        except Exception:
            # 出错时清理残留临时文件，不留下半状态；原 auth.json 未改，旧密码仍有效
            for tmp_path, _target in tmp_pairs:
                try:
                    if tmp_path.exists():
                        tmp_path.unlink()
                except OSError:
                    pass
            raise

        # 更新内存中的当前密钥
        self._password = new_password
        self._key = self._fernet_key_material(new_password, new_key_salt)
        self._fernet = new_fernet

        return True

    def _read_json(self, path: Path) -> Optional[Dict]:
        """
        读取并解密 JSON 文件

        Args:
            path: 文件路径

        Returns:
            解密后的 JSON 数据，如果文件不存在或解密失败则返回 None
        """
        if not path.exists():
            return None

        # auth.json 不加密
        if path.name == "auth.json":
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return None

        # 其他文件加密
        if self._fernet is None:
            return None

        try:
            with open(path, "rb") as f:
                encrypted_content = f.read()
            decrypted_content = self._fernet.decrypt(encrypted_content)
            return json.loads(decrypted_content.decode("utf-8"))
        except (InvalidToken, json.JSONDecodeError, IOError):
            return None

    @staticmethod
    def _atomic_write_bytes(path: Path, content: bytes) -> None:
        """二进制原子写入：临时文件写完并 fsync，再 os.replace 原子替换，避免半截损坏文件。"""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        with open(tmp_path, "wb") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)

    def _write_json(self, path: Path, data: Dict):
        """
        加密并原子写入 JSON 文件

        - auth.json 不加密，但同样走原子写入；
        - 其余文件先 Fernet 加密，再以 .tmp → fsync → os.replace 原子落盘，
          避免程序异常、磁盘满或中途终止时留下半截损坏密文（与未加密基类的原子写入对齐）。
        """
        path.parent.mkdir(parents=True, exist_ok=True)

        # auth.json 不加密
        if path.name == "auth.json":
            payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
            self._atomic_write_bytes(path, payload)
            return

        # 其他文件加密
        if self._fernet is None:
            raise ValueError("未设置密码，无法加密数据")

        json_content = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        encrypted_content = self._fernet.encrypt(json_content)
        self._atomic_write_bytes(path, encrypted_content)

    # ============================================================
    # 能力闸门（重写，返回加密模式）
    # ============================================================

    def get_storage_mode(self) -> str:
        """获取当前存储模式"""
        return "local_encrypted"

    def get_storage_capabilities(self) -> Dict[str, Any]:
        """获取存储能力"""
        return {
            "mode": "local_encrypted",
            "description": "加密的本地存储，所有用户数据使用 Fernet 对称加密",
            "encryption": {
                "algorithm": "Fernet (AES-128-CBC + HMAC-SHA256)",
                "key_derivation": "PBKDF2-HMAC-SHA256",
                "iterations": self.ITERATIONS,
            },
            "supports": {
                "profile": True,
                "insights": True,
                "conversations": True,
                "patterns": True,
                "reviews": True,
                "config": True,
                "progress": True,
                "delete_all": True,
                "password_change": True,
            },
            "limitations": {
                "password_recovery": False,
                "cloud_sync": False,
                "multi_device": False,
            },
        }
