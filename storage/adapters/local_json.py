"""
本地 JSON 文件存储适配器

实现 storage/README.md 中定义的抽象接口，使用本地 JSON 文件存储持久化档案。

当前运行模式：local_unencrypted（未加密的本地存储，高敏感内容建议不保存）

数据存储目录：storage/data/{user_id}/
- profile.json          生活风格画像（全量版）
- profile.lite.json     生活风格画像（精简注入版）
- config.json           用户配置（模块开关）
- progress.json         当前探索进度
- insights/             洞察卡目录
- conversations/        对话记录目录
- patterns/             模式卡目录
- reviews/              回顾报告目录
- deleted/              已删除文件目录（级联删除后移到这里，可恢复）

复用经验来源：
- know-yourself：全量版+精简注入版双档案设计、配置.json 模块开关、进度保存机制
- diarygpt：源—派生关系、检索前重验与删除失效（删除源记录时级联删除派生记录）
"""

import json
import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# 对话 ID 严格格式：只接受本系统生成器产出的 conversation-<12位hex>，
# 拒绝 ..、路径分隔符、绝对路径等，防止 --id 拼路径跳出 conversations/
CONVERSATION_ID_RE = re.compile(r"^conversation-[0-9a-f]{12}$")


def _is_valid_conversation_id(conv_id: str) -> bool:
    """对话 ID 是否为系统生成的合法格式（防路径遍历）。"""
    return isinstance(conv_id, str) and bool(CONVERSATION_ID_RE.match(conv_id))


# 全量扫描上限：级联删除、全删、统计时必须遍历全部记录，
# 不能被 list_* 默认分页（20）或硬编码上限截断，否则派生记录残留
FULL_SCAN_LIMIT = 1_000_000

# 摘要口吻检测：真实对话中 Skill 绝不会用这些第三人称元叙述开头来概括自己的回复
# （"深化目的论：…""引入纵向关系角度：…""输出暂定探索地图…"等都是摘要的典型指纹）
_SUMMARY_META_PREFIXES = (
    "深化", "引入", "输出", "基于", "发现", "如实回答",
    "阿德勒目的论", "阿德勒", "核心矛盾", "情绪与行为",
)


class LocalJsonStorageAdapter:
    """本地 JSON 文件存储适配器"""

    def __init__(self, base_dir: str = "storage/data", user_id: str = "default"):
        """
        初始化存储适配器

        Args:
            base_dir: 基础目录（默认 storage/data）
            user_id: 用户 ID（用于隔离不同用户的数据）
        """
        self.base_dir = Path(base_dir)
        self.user_id = user_id
        self.user_dir = self.base_dir / user_id
        self._ensure_directories()

        # P0-4 防加密/明文混用：该用户目录已启用加密（auth.json 存在）时，
        # 未加密适配器直接拒绝初始化。否则某次调用漏传 --storage-mode local_encrypted，
        # 数据就会以明文写进加密库，之后加密导出又读不到这批明文，静默丢数据。
        if (self.user_dir / "auth.json").exists():
            raise RuntimeError(
                "检测到该用户目录已启用加密存储（auth.json 存在）。"
                "请改用 --storage-mode local_encrypted 并通过环境变量 ADLERIAN_PASSWORD 提供密码访问；"
                "禁止以未加密模式写入，否则会产生明文与加密数据混用。"
            )

    def _ensure_directories(self):
        """确保所有必要的目录存在"""
        dirs = [
            self.user_dir,
            self.user_dir / "insights",
            self.user_dir / "conversations",
            self.user_dir / "patterns",
            self.user_dir / "reviews",
            self.user_dir / "deleted",
            self.user_dir / "deleted" / "insights",
            self.user_dir / "deleted" / "conversations",
            self.user_dir / "deleted" / "patterns",
            self.user_dir / "deleted" / "reviews",
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)

    def _now(self) -> str:
        """获取当前时间（ISO 8601 格式）"""
        return datetime.now().isoformat()

    def _generate_id(self, prefix: str) -> str:
        """生成唯一 ID"""
        return f"{prefix}-{uuid.uuid4().hex[:12]}"

    def _read_json(self, path: Path) -> Optional[Dict]:
        """读取 JSON 文件"""
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None

    def _write_json(self, path: Path, data: Dict):
        """
        写入 JSON 文件（原子写入）

        使用"临时文件写完 → fsync → 原子替换"的方式，
        避免程序异常、磁盘满或中途终止时档案损坏。

        Args:
            path: 文件路径
            data: 要写入的 JSON 数据
        """
        path.parent.mkdir(parents=True, exist_ok=True)

        # 写入临时文件
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())

        # 原子替换（os.replace 在 Windows 和 Linux 上都是原子操作）
        os.replace(tmp_path, path)

    def _move_to_deleted(self, path: Path, subdir: str):
        """
        将文件移到已删除目录

        如果目标文件已存在，先删除目标文件（保留最新的删除记录）。
        """
        if not path.exists():
            return
        deleted_path = self.user_dir / "deleted" / subdir / path.name
        deleted_path.parent.mkdir(parents=True, exist_ok=True)
        # 如果目标文件已存在，先删除
        if deleted_path.exists():
            deleted_path.unlink()
        path.rename(deleted_path)

    # ============================================================
    # 完整对话记录硬校验（适配器层最后一道防线，任何写入入口都逃不过）
    # ============================================================

    def _validate_full_transcript(self, messages: List[Dict], source: Any = None):
        """
        适配器层硬校验：完整对话记录必须通过这些校验才能落盘。

        这是最后一道防线——无论调用方是 save_conversation.py 脚本，
        还是 Skill 直接 import 适配器写入，都必须通过本校验。
        校验不通过直接抛 ValueError，拒绝写入。

        校验项：
        1. 来源凭证：如果提供了 source，必须是 conversation_history
        2. 真实时间戳：每条必须有可解析的时间戳，单调不减
        3. 角色对等：user 与 assistant 数量差 ≤ 2
        4. 交替性：不允许连续3条同角色
        5. 摘要口吻检测：assistant 消息不能是第三人称概括
           （真实对话中 Skill 绝不会说"问用户：…"，也不会以"深化/引入/输出"开头做要点归纳）

        Args:
            messages: 消息列表 [{role, content, timestamp}, ...]
            source: 来源凭证（dict 或字符串），None 表示不校验来源

        Raises:
            ValueError: 任何一项校验不通过
        """
        if not messages:
            return  # 空消息列表不校验（可能是只存摘要的记录）

        errors = []

        # 校验1：来源凭证
        if source is not None:
            if isinstance(source, dict):
                method = source.get("method", source.get("source", ""))
            else:
                method = str(source)
            if method and method != "conversation_history":
                errors.append(
                    f"完整对话来源必须是 conversation_history（会话历史工具拉取），"
                    f"当前为 {method!r}。严禁凭模型记忆或画像摘要重构对话。"
                )

        # 校验2：真实时间戳
        parsed_ts = []
        for i, m in enumerate(messages):
            ts = m.get("timestamp")
            if not ts or (isinstance(ts, str) and not ts.strip()):
                errors.append(f"第 {i+1} 条消息缺少真实 timestamp（必须用会话历史里的 created_at）")
                continue
            try:
                s = str(ts).strip().replace("Z", "+00:00")
                if "T" not in s:
                    parsed_ts.append(datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S"))
                else:
                    dt = datetime.fromisoformat(s)
                    if dt.tzinfo is not None:
                        dt = dt.replace(tzinfo=None)
                    parsed_ts.append(dt)
            except Exception:
                errors.append(f"第 {i+1} 条消息的 timestamp 无法解析：{ts!r}")

        if len(parsed_ts) >= 2:
            for i in range(1, len(parsed_ts)):
                if parsed_ts[i] < parsed_ts[i - 1]:
                    errors.append(f"第 {i+1} 条消息时间戳早于前一条（消息未按时间排序）")
                    break

        # 校验3：角色对等
        user_n = sum(1 for m in messages if m.get("role") == "user")
        asst_n = sum(1 for m in messages if m.get("role") == "assistant")
        if user_n == 0:
            errors.append("没有任何用户消息，不可能是完整对话记录")
        if asst_n == 0:
            errors.append("没有任何 Skill 回复消息——完整对话必须包含 Skill 每一轮的回复原文")
        if abs(user_n - asst_n) > 2:
            errors.append(
                f"角色严重不对等：用户 {user_n} 条、Skill {asst_n} 条（差 {abs(user_n - asst_n)} 条）。"
                f"真实对话一来一回，数量应基本相等。"
            )

        # 校验4：交替性（不允许连续超过2条同角色）
        if messages:
            run_role, run_len = messages[0].get("role"), 1
            for m in messages[1:]:
                if m.get("role") == run_role:
                    run_len += 1
                    if run_len > 2:
                        errors.append(f"存在连续 {run_len} 条 {run_role} 消息——真实对话按时间交替推进")
                        break
                else:
                    run_role, run_len = m.get("role"), 1

        # 校验5：摘要口吻检测（assistant 消息不能是第三人称概括）
        asst_msgs = [m for m in messages if m.get("role") == "assistant"]
        if asst_msgs:
            # 5a. 强特征：assistant 消息中出现"问用户："——真实对话绝不会这样说
            for i, m in enumerate(messages):
                if m.get("role") == "assistant" and "问用户：" in m.get("content", ""):
                    errors.append(
                        f"第 {i+1} 条 Skill 回复中出现\"问用户：\"——这是第三人称概括的铁证，"
                        f"真实对话中 Skill 绝不会这样表述。请用会话历史原文，不要概括。"
                    )
                    break

            # 5b. 元叙述关键词开头 + 短消息（超过半数即判为摘要）
            meta_hits = 0
            for m in asst_msgs:
                content = m.get("content", "").strip()
                if len(content) < 250 and any(content.startswith(p) for p in _SUMMARY_META_PREFIXES):
                    meta_hits += 1
            if len(asst_msgs) >= 4 and meta_hits > len(asst_msgs) / 2:
                errors.append(
                    f"检测到摘要式概括：{len(asst_msgs)} 条 Skill 回复中有 {meta_hits} 条"
                    f"以\"深化/引入/输出/基于/发现\"等元叙述开头且长度不足250字。"
                    f"这是把 Skill 回复压缩成要点归纳的特征，不是逐字原文。"
                )

        if errors:
            raise ValueError(
                "完整对话记录校验未通过，已拒绝保存：\n" +
                "\n".join(f"  - {e}" for e in errors)
            )

    # ============================================================
    # 能力闸门
    # ============================================================

    def get_storage_mode(self) -> str:
        """
        获取当前存储模式

        Returns:
            local_unencrypted（未加密的本地存储）
        """
        return "local_unencrypted"

    def get_storage_capabilities(self) -> Dict[str, bool]:
        """
        获取存储能力

        Returns:
            能力字典
        """
        return {
            "can_persist": True,
            "can_edit_delete": True,
            "can_read_cross_session": True,
            "can_store_high_sensitivity": False,  # 未加密，不建议存储高敏感内容
            "can_private_vault": False,  # 未实现加密私密库
            "can_full_lock": False,  # 未实现全量锁定
            "can_recover": True,  # 已删除文件移到 deleted/ 目录，可恢复
        }

    # ============================================================
    # 档案读写（生活风格画像）
    # ============================================================

    def read_profile(self, lite: bool = False) -> Dict:
        """
        读取生活风格画像

        Args:
            lite: 是否读取精简注入版

        Returns:
            生活风格画像数据，如果不存在则返回空结构
        """
        filename = "profile.lite.json" if lite else "profile.json"
        path = self.user_dir / filename
        data = self._read_json(path)
        if data is None:
            # 返回空结构
            data = {
                "id": self._generate_id("profile"),
                "type": "profile_lite" if lite else "profile",
                "sensitivity_level": "medium",
                "source": "initial-assessment",
                "version": 1,
                "created_at": self._now(),
                "updated_at": self._now(),
                "deleted": False,
                "deleted_at": None,
                "profile_status": "not_initialized",  # 画像状态：not_initialized（未初始化）/ partial（部分画像，只有零散洞察）/ initialized（已完成初步画像建立）
                "current_focus": {
                    "current_topic": "",
                    "response_preference": "",
                    "last_updated": "",
                },
                "confirmed_understandings": [],
                "pending_understandings": [],
                "trigger_boundaries": {
                    "sensitive_topics": "",
                    "preferred_response_style": "",
                    "unwanted_surprises": "",
                    "support_preferences": "",
                },
                "strengths_and_values": {
                    "existing_strengths": "",
                    "values_to_keep": "",
                    "directions_to_explore": "",
                },
                "confirmed_patterns": [],
                "lifestyle_overview": {
                    "core_summary": "",
                    "key_themes": [],
                    "confidence": "",
                    "note": "",
                    "created_at": "",
                    "last_updated": "",
                },
                "core_dimensions": {
                    "self_concept": {
                        "core_belief": "",
                        "details": [],
                        "source": "",
                        "confidence": "",
                        "user_correction": "",
                        "last_updated": "",
                    },
                    "self_ideal": {
                        "core_belief": "",
                        "details": [],
                        "source": "",
                        "confidence": "",
                        "user_correction": "",
                        "last_updated": "",
                    },
                    "world_view": {
                        "core_belief": "",
                        "details": [],
                        "source": "",
                        "confidence": "",
                        "user_correction": "",
                        "last_updated": "",
                    },
                    "view_of_others": {
                        "core_belief": "",
                        "details": [],
                        "source": "",
                        "confidence": "",
                        "user_correction": "",
                        "last_updated": "",
                    },
                    "private_logic": {
                        "core_belief": "",
                        "details": [],
                        "source": "",
                        "confidence": "",
                        "user_correction": "",
                        "last_updated": "",
                    },
                    "basic_mistakes": {
                        "core_belief": "",
                        "details": [],
                        "source": "",
                        "confidence": "",
                        "user_correction": "",
                        "last_updated": "",
                    },
                    "behavioral_strategies": {
                        "core_belief": "",
                        "details": [],
                        "source": "",
                        "confidence": "",
                        "user_correction": "",
                        "last_updated": "",
                    },
                    "social_interest": {
                        "core_belief": "",
                        "details": [],
                        "source": "",
                        "confidence": "",
                        "user_correction": "",
                        "last_updated": "",
                    },
                    "inferiority_and_compensation": {
                        "core_belief": "",
                        "details": [],
                        "source": "",
                        "confidence": "",
                        "user_correction": "",
                        "last_updated": "",
                    },
                },
                "change_log": [],
                # D模块：画像进化架构
                "pending_core_belief_updates": [],  # 待用户确认的核心信念变更（不自动覆盖）
                "pending_conflicts": [],  # 待校正的冲突（情境差异/真矛盾）
            }
        return data

    def _is_empty_profile(self, profile: Dict) -> bool:
        """
        判断画像是否为空画像

        空画像的判断标准：
        - confirmed_understandings 为空列表
        - pending_understandings 为空列表
        - confirmed_patterns 为空列表
        - version 为 1 或不存在
        - strengths_and_values 中的 existing_strengths 为空字符串

        Args:
            profile: 生活风格画像数据

        Returns:
            True 如果是空画像，False 否则
        """
        confirmed = profile.get("confirmed_understandings", [])
        pending = profile.get("pending_understandings", [])
        patterns = profile.get("confirmed_patterns", [])
        version = profile.get("version", 1)
        strengths = profile.get("strengths_and_values", {})
        existing_strengths = strengths.get("existing_strengths", "")

        # 如果所有核心内容都为空，且版本为1，则认为是空画像
        return (
            len(confirmed) == 0
            and len(pending) == 0
            and len(patterns) == 0
            and version <= 1
            and not existing_strengths
        )

    def write_profile(self, profile: Dict, lite: bool = False, force_overwrite: bool = False):
        """
        写入生活风格画像

        安全保护：如果文件已存在且非空，且传入的画像结构是空的，
        则拒绝覆盖并抛出异常，防止误操作覆盖已有画像。
        只有显式传入 force_overwrite=True 时才允许覆盖非空文件。

        Args:
            profile: 生活风格画像数据
            lite: 是否写入精简注入版
            force_overwrite: 是否强制覆盖非空文件（默认 False）

        Raises:
            ValueError: 如果尝试用空画像覆盖非空文件且 force_overwrite=False
        """
        filename = "profile.lite.json" if lite else "profile.json"
        path = self.user_dir / filename

        # 安全保护：检查是否尝试用空画像覆盖非空文件
        if path.exists() and not force_overwrite:
            existing_data = self._read_json(path)
            if existing_data is not None and not self._is_empty_profile(existing_data):
                # 已有非空画像
                if self._is_empty_profile(profile):
                    # 尝试用空画像覆盖非空画像，拒绝
                    raise ValueError(
                        "安全保护：拒绝用空画像覆盖已有的非空画像。"
                        "如果确实需要覆盖，请传入 force_overwrite=True。"
                    )

        # 在覆盖前，先将旧文件移到 deleted/ 目录作为可恢复副本
        if path.exists():
            self._move_to_deleted(path, "")

        profile["updated_at"] = self._now()
        profile["version"] = profile.get("version", 1) + 1
        self._write_json(path, profile)

        # 如果写入全量版，同步更新精简版
        if not lite:
            self._sync_lite_profile(profile)

    def _sync_lite_profile(self, full_profile: Dict):
        """
        同步精简注入版画像（只包含当前对话需要的关键信息）

        复用 know-yourself 的双档案设计经验：全量版用于完整存储，精简版用于对话上下文注入。

        Args:
            full_profile: 全量版画像数据
        """
        lite_profile = {
            "id": full_profile.get("id"),
            "type": "profile_lite",
            "version": full_profile.get("version", 1),
            "updated_at": self._now(),
            # 只包含关键信息
            "current_focus": full_profile.get("current_focus", {}),
            "confirmed_understandings": full_profile.get("confirmed_understandings", []),
            "trigger_boundaries": full_profile.get("trigger_boundaries", {}),
            "strengths_and_values": full_profile.get("strengths_and_values", {}),
            # 生活风格概览和核心维度（画像驱动对话需要）
            "lifestyle_overview": full_profile.get("lifestyle_overview", {}),
            "core_dimensions": full_profile.get("core_dimensions", {}),
        }
        path = self.user_dir / "profile.lite.json"
        self._write_json(path, lite_profile)

    def update_profile_section(self, section: str, data: Any):
        """
        更新画像的指定部分

        Args:
            section: 部分名称（current_focus / confirmed_understandings / pending_understandings / trigger_boundaries / strengths_and_values / confirmed_patterns / lifestyle_overview / core_dimensions）
            data: 要更新的数据
        """
        profile = self.read_profile()
        profile[section] = data
        # 记录变更日志
        change_log = profile.get("change_log", [])
        change_log.append({
            "id": self._generate_id("change"),
            "date": self._now()[:10],
            "change_type": "modify",
            "user_modification": f"更新 {section}",
            "processing_notes": "通过 update_profile_section 更新",
        })
        profile["change_log"] = change_log
        self.write_profile(profile)

    # ============================================================
    # D模块：画像自动累积更新（洞察 → 核心维度）
    # ============================================================

    def accumulate_insight_to_profile(self, insight: Dict) -> Dict:
        """
        将已确认的洞察自动累积到生活风格画像的对应核心维度。

        双层更新机制：
        - details（细节层）：自动追加，不需要用户额外确认（去重）
        - core_belief（核心信念层）：变更必须用户确认，不自动覆盖，
          加入 pending_core_belief_updates 列表，下次对话时呈现给用户判断

        冲突检测：
        - 情境差异（context_difference）：不同情境下的不同表现，不是真矛盾
        - 真矛盾（true_conflict）：同一情境下观点相反，加入 pending_conflicts

        洞察数据中可传入的控制字段：
        - related_dimensions: 关联的核心维度键列表（必需，用于 details 自动追加）
        - context_tags: 情境标签列表（可选，如 ["work", "social"]）
        - suggests_core_belief_update: 是否建议更新核心信念（可选，默认 False）
        - core_belief_update_content: 建议的新核心信念内容（可选）
        - conflicts_with_existing: 是否与现有理解冲突（可选，默认 False）
        - conflict_type: 冲突类型（context_difference / true_conflict，可选）

        Args:
            insight: 洞察卡数据（已保存的完整洞察）

        Returns:
            更新结果摘要：updated_dimensions / details_added /
            pending_core_belief_updates / pending_conflicts
        """
        result = {
            "updated_dimensions": [],
            "details_added": 0,
            "pending_core_belief_updates": 0,
            "pending_conflicts": 0,
        }

        related_dimensions = insight.get("related_dimensions", [])
        if not related_dimensions:
            return result

        profile = self.read_profile()
        core_dimensions = profile.get("core_dimensions", {})

        # 洞察的核心内容
        insight_title = insight.get("title", "")
        insight_content = insight.get("content", insight.get("shared_summary", ""))
        insight_id = insight.get("id", "")
        context_tags = insight.get("context_tags", [])
        confidence = insight.get("confidence", "中")

        # 构造细节条目（带情境标签的对象格式，向后兼容字符串）
        detail_content = f"{insight_title}：{insight_content}" if insight_title else insight_content
        detail_entry = {
            "content": detail_content,
            "context_tags": context_tags,
            "source_insight_id": insight_id,
            "created_at": self._now(),
        }

        for dim_key in related_dimensions:
            if dim_key not in core_dimensions:
                # 不匹配的维度键名，打印警告而不是静默跳过
                valid_dims = sorted(core_dimensions.keys())
                print(f"⚠️ 警告：洞察卡的 related_dimensions 包含非法键名 '{dim_key}'，已跳过。")
                print(f"   合法的维度键名: {valid_dims}")
                print(f"   请检查洞察卡的 related_dimensions 字段，使用正确的键名。")
                continue

            dim = core_dimensions[dim_key]
            existing_details = dim.get("details", [])

            # ---- 1. details 自动追加（去重）----
            is_duplicate = False
            for existing in existing_details:
                # 支持字符串和对象两种格式
                existing_content = existing if isinstance(existing, str) else existing.get("content", "")
                if existing_content and detail_content and (
                    detail_content in existing_content or existing_content in detail_content
                ):
                    is_duplicate = True
                    break

            if not is_duplicate and detail_content:
                existing_details.append(detail_entry)
                dim["details"] = existing_details
                result["details_added"] += 1

            # ---- 2. core_belief 变更检测（需用户确认，不自动覆盖）----
            existing_core_belief = dim.get("core_belief", "")
            if insight.get("suggests_core_belief_update", False):
                new_belief = insight.get("core_belief_update_content", insight_content)
                if new_belief and new_belief != existing_core_belief:
                    pending_updates = profile.get("pending_core_belief_updates", [])
                    # 避免重复加入同一维度的相同建议
                    already_pending = any(
                        p.get("dimension") == dim_key and p.get("new_belief") == new_belief
                        for p in pending_updates
                    )
                    if not already_pending:
                        pending_updates.append({
                            "id": self._generate_id("pending_update"),
                            "dimension": dim_key,
                            "dimension_name": self._get_dimension_display_name(dim_key),
                            "new_belief": new_belief,
                            "old_belief": existing_core_belief,
                            "source_insight_id": insight_id,
                            "context_tags": context_tags,
                            "created_at": self._now(),
                            "status": "pending",
                        })
                        profile["pending_core_belief_updates"] = pending_updates
                        result["pending_core_belief_updates"] += 1

            # ---- 3. 冲突检测（情境差异 vs 真矛盾）----
            if insight.get("conflicts_with_existing", False):
                pending_conflicts = profile.get("pending_conflicts", [])
                conflict_type = insight.get("conflict_type", "true_conflict")
                already_pending = any(
                    c.get("dimension") == dim_key
                    and c.get("new_understanding") == insight_content
                    for c in pending_conflicts
                )
                if not already_pending:
                    pending_conflicts.append({
                        "id": self._generate_id("conflict"),
                        "dimension": dim_key,
                        "dimension_name": self._get_dimension_display_name(dim_key),
                        "old_understanding": existing_core_belief or "（暂无核心信念）",
                        "new_understanding": insight_content,
                        "context_tags": context_tags,
                        "source_insight_id": insight_id,
                        "created_at": self._now(),
                        "conflict_type": conflict_type,  # context_difference / true_conflict
                        "status": "pending",
                    })
                    profile["pending_conflicts"] = pending_conflicts
                    result["pending_conflicts"] += 1

            # ---- 4. 更新 source、confidence、last_updated ----
            existing_source = dim.get("source", "")
            new_source = f"日常对话-{self._now()[:10]}"
            if existing_source:
                if new_source not in existing_source:
                    dim["source"] = f"{existing_source}、{new_source}"
            else:
                dim["source"] = new_source

            # 置信度调整：不冲突的新证据可提升置信度（低→中，中→高）
            if not insight.get("conflicts_with_existing", False):
                current_confidence = dim.get("confidence", "")
                if current_confidence == "低" and confidence in ("中", "高"):
                    dim["confidence"] = "中"
                elif current_confidence == "中" and confidence == "高":
                    dim["confidence"] = "高"

            dim["last_updated"] = self._now()
            result["updated_dimensions"].append(dim_key)

        # ---- 5. 画像状态自动更新 ----
        # 如果画像还未初始化（not_initialized），且有洞察累积进来，自动改为 partial（部分画像）
        # 这样用户先进行探索性对话再保存时，不会被误认为已完成初步画像建立
        if result["updated_dimensions"] or result["pending_core_belief_updates"] or result["pending_conflicts"]:
            current_status = profile.get("profile_status", "not_initialized")
            if current_status == "not_initialized":
                profile["profile_status"] = "partial"
                result["status_changed_to"] = "partial"

        # ---- 6. 保存更新后的画像 ----
        if result["updated_dimensions"] or result["pending_core_belief_updates"] or result["pending_conflicts"]:
            change_log = profile.get("change_log", [])
            change_log.append({
                "id": self._generate_id("change"),
                "date": self._now()[:10],
                "change_type": "auto_accumulate",
                "user_modification": (
                    f"洞察自动累积到画像：更新{len(result['updated_dimensions'])}个维度，"
                    f"追加{result['details_added']}条细节，"
                    f"待确认核心信念{result['pending_core_belief_updates']}项，"
                    f"待校正冲突{result['pending_conflicts']}项"
                ),
                "processing_notes": f"来源洞察：{insight_id}",
            })
            profile["change_log"] = change_log
            self.write_profile(profile)

        return result

    def get_profile_status(self) -> str:
        """
        获取画像状态。

        Returns:
            画像状态字符串：
            - not_initialized：未初始化（完全空画像，没有任何内容）
            - partial：部分画像（用户还没有走初步画像建立工作流，但已经通过探索性对话保存了一些零散洞察）
            - initialized：已完成初步画像建立（通过专门的初步画像建立工作流系统建立，9个核心维度都有内容，有生活风格概览）
        """
        profile = self.read_profile()
        return profile.get("profile_status", "not_initialized")

    def set_profile_status(self, status: str):
        """
        设置画像状态。

        Args:
            status: 画像状态 - not_initialized / partial / initialized
        """
        valid_statuses = ("not_initialized", "partial", "initialized")
        if status not in valid_statuses:
            raise ValueError(f"无效的画像状态：{status}，必须是 {valid_statuses} 之一")
        profile = self.read_profile()
        profile["profile_status"] = status
        change_log = profile.get("change_log", [])
        change_log.append({
            "id": self._generate_id("change"),
            "date": self._now()[:10],
            "change_type": "status_change",
            "user_modification": f"画像状态变更为：{status}",
            "processing_notes": "通过 set_profile_status 设置",
        })
        profile["change_log"] = change_log
        self.write_profile(profile)

    def _get_dimension_display_name(self, dim_key: str) -> str:
        """获取核心维度的中文显示名称"""
        names = {
            "self_concept": "自我概念",
            "self_ideal": "理想自我",
            "world_view": "世界观",
            "view_of_others": "他人观",
            "private_logic": "私人逻辑",
            "basic_mistakes": "基本错误",
            "behavioral_strategies": "行为策略",
            "social_interest": "社会兴趣",
            "inferiority_and_compensation": "自卑感与补偿方式",
        }
        return names.get(dim_key, dim_key)

    def resolve_pending_core_belief_update(self, update_id: str, action: str, user_text: str = ""):
        """
        处理待确认的核心信念变更。

        Args:
            update_id: 待确认项 ID
            action: 处理方式 - accept（接受新信念，覆盖core_belief）/
                    keep（保留旧信念，标记新信念为特定情境表现）/
                    both（两者都保留，标注情境差异）/
                    custom（用户自定义修正）
            user_text: 用户自定义的修正内容（action=custom 时使用）
        """
        profile = self.read_profile()
        pending = profile.get("pending_core_belief_updates", [])
        for item in pending:
            if item.get("id") == update_id:
                dim_key = item.get("dimension")
                dim = profile.get("core_dimensions", {}).get(dim_key, {})

                if action == "accept":
                    dim["core_belief"] = item.get("new_belief", "")
                    dim["last_updated"] = self._now()
                elif action == "keep":
                    # 保留旧信念，把新信念作为细节加入（标注为特定情境表现）
                    new_detail = {
                        "content": f"[特定情境表现] {item.get('new_belief', '')}",
                        "context_tags": item.get("context_tags", []),
                        "source_insight_id": item.get("source_insight_id", ""),
                        "created_at": self._now(),
                    }
                    dim.setdefault("details", []).append(new_detail)
                elif action == "both":
                    # 两者都保留，标注情境差异
                    new_detail = {
                        "content": f"[情境差异-另一情境表现] {item.get('new_belief', '')}",
                        "context_tags": item.get("context_tags", []),
                        "source_insight_id": item.get("source_insight_id", ""),
                        "created_at": self._now(),
                    }
                    dim.setdefault("details", []).append(new_detail)
                elif action == "custom" and user_text:
                    dim["core_belief"] = user_text
                    dim["last_updated"] = self._now()

                item["status"] = f"resolved_{action}"
                item["resolved_at"] = self._now()
                item["user_text"] = user_text
                break

        # 记录变更日志
        change_log = profile.get("change_log", [])
        change_log.append({
            "id": self._generate_id("change"),
            "date": self._now()[:10],
            "change_type": "resolve_pending_update",
            "user_modification": f"处理待确认核心信念变更：{action}",
            "processing_notes": f"待确认项：{update_id}",
        })
        profile["change_log"] = change_log
        self.write_profile(profile)

    def resolve_pending_conflict(self, conflict_id: str, action: str, user_text: str = ""):
        """
        处理待校正的冲突。

        Args:
            conflict_id: 冲突项 ID
            action: 处理方式 - accept_new（接受新理解）/ keep_old（保留旧理解）/
                    context_diff（确认为情境差异，两者都保留）/ custom（用户自定义）
            user_text: 用户自定义的修正内容
        """
        profile = self.read_profile()
        conflicts = profile.get("pending_conflicts", [])
        for item in conflicts:
            if item.get("id") == conflict_id:
                dim_key = item.get("dimension")
                dim = profile.get("core_dimensions", {}).get(dim_key, {})

                if action == "accept_new":
                    dim["core_belief"] = item.get("new_understanding", "")
                    dim["last_updated"] = self._now()
                elif action == "keep_old":
                    # 保留旧理解，把新理解作为细节加入
                    new_detail = {
                        "content": f"[已排除-不适用] {item.get('new_understanding', '')}",
                        "context_tags": item.get("context_tags", []),
                        "source_insight_id": item.get("source_insight_id", ""),
                        "created_at": self._now(),
                    }
                    dim.setdefault("details", []).append(new_detail)
                elif action == "context_diff":
                    # 确认为情境差异，两者都保留
                    new_detail = {
                        "content": f"[情境差异] {item.get('new_understanding', '')}",
                        "context_tags": item.get("context_tags", []),
                        "source_insight_id": item.get("source_insight_id", ""),
                        "created_at": self._now(),
                    }
                    dim.setdefault("details", []).append(new_detail)
                elif action == "custom" and user_text:
                    dim["core_belief"] = user_text
                    dim["last_updated"] = self._now()

                item["status"] = f"resolved_{action}"
                item["resolved_at"] = self._now()
                item["user_text"] = user_text
                break

        change_log = profile.get("change_log", [])
        change_log.append({
            "id": self._generate_id("change"),
            "date": self._now()[:10],
            "change_type": "resolve_conflict",
            "user_modification": f"处理待校正冲突：{action}",
            "processing_notes": f"冲突项：{conflict_id}",
        })
        profile["change_log"] = change_log
        self.write_profile(profile)

    # ============================================================
    # 洞察卡
    # ============================================================

    def append_insight(self, insight: Dict, auto_update_profile: bool = True) -> str:
        """
        追加洞察卡

        Args:
            insight: 洞察卡数据
            auto_update_profile: 是否自动将洞察累积到生活风格画像的对应核心维度
                （默认 True；仅当 user_confirmed=True 且有 related_dimensions 时才会实际更新）

        Returns:
            洞察卡 ID
        """
        # 校验 related_dimensions 是否为合法的维度键名
        valid_dimensions = {
            "self_concept", "self_ideal", "world_view", "view_of_others", "private_logic",
            "basic_mistakes", "behavioral_strategies", "social_interest", "inferiority_and_compensation"
        }
        related_dimensions = insight.get("related_dimensions", [])
        if related_dimensions:
            invalid_dims = [d for d in related_dimensions if d not in valid_dimensions]
            if invalid_dims:
                print(f"⚠️ 警告：洞察卡的 related_dimensions 包含非法键名: {invalid_dims}")
                print(f"   合法的9个维度键名: {sorted(valid_dimensions)}")
                print(f"   这些非法维度将不会被累积到画像中。请修正后重新保存。")

        insight_id = insight.get("id", self._generate_id("insight"))
        insight["id"] = insight_id
        insight["type"] = "insight"
        insight["created_at"] = insight.get("created_at", self._now())
        insight["updated_at"] = self._now()
        insight["deleted"] = False
        insight["deleted_at"] = None

        path = self.user_dir / "insights" / f"{insight_id}.json"
        self._write_json(path, insight)

        # D模块：保存洞察后自动累积到画像（仅当用户已确认且有关联维度时）
        if auto_update_profile and insight.get("user_confirmed", False) and insight.get("related_dimensions"):
            try:
                self.accumulate_insight_to_profile(insight)
            except Exception as e:
                # 画像累积失败不影响洞察保存，记录错误但不抛出
                print(f"[警告] 洞察自动累积到画像失败（不影响洞察保存）：{e}")

        return insight_id

    def list_insights(self, limit: int = 20, since: Optional[str] = None) -> List[Dict]:
        """
        列出洞察卡

        Args:
            limit: 返回数量限制
            since: 只返回此时间之后的洞察

        Returns:
            洞察卡列表（按创建时间倒序）
        """
        insights_dir = self.user_dir / "insights"
        insights = []
        for f in insights_dir.glob("*.json"):
            data = self._read_json(f)
            if data and not data.get("deleted", False):
                if since and data.get("created_at", "") < since:
                    continue
                insights.append(data)
        # 按创建时间倒序
        insights.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return insights[:limit]

    def get_insight(self, insight_id: str) -> Optional[Dict]:
        """
        获取单个洞察卡

        Args:
            insight_id: 洞察卡 ID

        Returns:
            洞察卡数据，如果不存在或已删除则返回 None
        """
        path = self.user_dir / "insights" / f"{insight_id}.json"
        data = self._read_json(path)
        if data and not data.get("deleted", False):
            return data
        return None

    def delete_insight(self, insight_id: str, cascade: bool = True):
        """
        删除洞察卡

        复用 diarygpt 的源—派生关系经验：删除源洞察卡时，重新评估相关模式卡的证据门槛。

        Args:
            insight_id: 洞察卡 ID
            cascade: 是否级联处理（重新评估模式卡证据门槛）
        """
        path = self.user_dir / "insights" / f"{insight_id}.json"
        if path.exists():
            self._move_to_deleted(path, "insights")

        if cascade:
            # 重新评估所有引用此洞察卡的模式卡
            patterns = self.list_patterns()
            for pattern in patterns:
                source_insights = pattern.get("source_insight_ids", [])
                if insight_id in source_insights:
                    # 从源洞察卡列表中移除
                    source_insights.remove(insight_id)
                    pattern["source_insight_ids"] = source_insights

                    # 重新评估证据门槛
                    evidence = pattern.get("evidence", {})
                    evidence["supporting_insights"] = [
                        i for i in evidence.get("supporting_insights", [])
                        if i != insight_id
                    ]
                    evidence["instance_count"] = len(evidence["supporting_insights"])
                    pattern["evidence"] = evidence

                    # 如果证据不足（少于3个独立实例），降为待验证或删除
                    if evidence["instance_count"] < 3:
                        pattern["status"] = "pending_verification"
                        pattern["downgraded_reason"] = f"洞察卡 {insight_id} 被删除，证据不足3个独立实例"

                    self.write_pattern(pattern)

    # ============================================================
    # 对话记录
    # ============================================================

    def append_conversation(self, entry: Dict) -> str:
        """
        追加对话记录

        Args:
            entry: 对话记录数据

        Returns:
            对话记录 ID
        """
        conv_id = entry.get("id", self._generate_id("conversation"))
        entry["id"] = conv_id
        entry["type"] = "conversation"
        entry["created_at"] = entry.get("created_at", self._now())
        entry["updated_at"] = self._now()
        entry["deleted"] = False
        entry["deleted_at"] = None

        # 确保完整对话记录字段存在（默认启用）
        if "full_transcript" not in entry:
            entry["full_transcript"] = {
                "enabled": True,
                "messages": [],
                "message_count": 0,
                "saved_at": self._now(),
            }
        else:
            # 如果传入了完整对话记录，确保字段完整
            ft = entry["full_transcript"]
            ft.setdefault("enabled", True)
            ft.setdefault("messages", [])
            ft.setdefault("message_count", len(ft.get("messages", [])))
            ft.setdefault("saved_at", self._now())

        # 【适配器层硬校验】如果有完整对话消息，必须通过校验（最后一道防线，任何写入入口都逃不过）
        messages = entry["full_transcript"].get("messages", [])
        if messages:
            source = entry["full_transcript"].get("source")
            self._validate_full_transcript(messages, source=source)

        path = self.user_dir / "conversations" / f"{conv_id}.json"
        self._write_json(path, entry)
        return conv_id

    def list_conversations(self, limit: int = 20, since: Optional[str] = None) -> List[Dict]:
        """
        列出对话记录

        Args:
            limit: 返回数量限制
            since: 只返回此时间之后的对话

        Returns:
            对话记录列表（按创建时间倒序）
        """
        conv_dir = self.user_dir / "conversations"
        conversations = []
        for f in conv_dir.glob("*.json"):
            data = self._read_json(f)
            if data and not data.get("deleted", False):
                if since and data.get("created_at", "") < since:
                    continue
                conversations.append(data)
        conversations.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return conversations[:limit]

    def search_conversations(self, query: str, limit: int = 10) -> List[Dict]:
        """
        搜索对话记录

        Args:
            query: 搜索关键词
            limit: 返回数量限制

        Returns:
            匹配的对话记录列表
        """
        conversations = self.list_conversations(limit=100)
        results = []
        for conv in conversations:
            summary = conv.get("summary", "")
            if query.lower() in summary.lower():
                results.append(conv)
            if len(results) >= limit:
                break
        return results

    def get_conversation(self, conv_id: str) -> Optional[Dict]:
        """获取单个对话记录"""
        if not _is_valid_conversation_id(conv_id):
            return None
        path = self.user_dir / "conversations" / f"{conv_id}.json"
        data = self._read_json(path)
        if data and not data.get("deleted", False):
            return data
        return None

    def append_conversation_messages(self, conv_id: str, messages: List[Dict]) -> Dict:
        """
        向已存在的对话记录追加完整对话消息（用于超长对话分段写入逐字原文）。

        Args:
            conv_id: 已存在的对话记录 ID
            messages: 要追加的消息列表 [{role, content, timestamp?}, ...]

        Returns:
            追加后的 full_transcript 统计信息

        Raises:
            KeyError: 对话记录不存在
            ValueError: messages 为空或格式非法
        """
        conv = self.get_conversation(conv_id)
        if conv is None:
            raise KeyError(f"对话记录不存在：{conv_id}，无法追加消息（请先用 append_conversation 创建）")
        if not isinstance(messages, list) or not messages:
            raise ValueError("要追加的 messages 必须是非空列表")

        ft = conv.setdefault("full_transcript", {
            "enabled": True, "messages": [], "message_count": 0, "saved_at": self._now(),
        })
        ft.setdefault("enabled", True)
        ft.setdefault("messages", [])

        valid_roles = {"user", "assistant"}
        for m in messages:
            role = m.get("role")
            content = m.get("content")
            if role not in valid_roles:
                raise ValueError(f"非法 role：{role}（只允许 user/assistant）")
            if not isinstance(content, str) or not content.strip():
                raise ValueError("每条消息的 content 必须是非空字符串（逐字原文，不能是摘要占位）")
            ts = m.get("timestamp")
            if not ts:
                raise ValueError("每条消息必须带会话历史返回的真实 timestamp（created_at），适配器不再自动补当前时间")
            ft["messages"].append({
                "role": role,
                "content": content,
                "timestamp": ts,
            })

        ft["message_count"] = len(ft["messages"])
        ft["saved_at"] = self._now()
        conv["updated_at"] = self._now()

        # 【适配器层硬校验】追加后对合并后的完整序列重新做整体校验
        source = conv.get("full_transcript", {}).get("source")
        self._validate_full_transcript(ft["messages"], source=source)

        path = self.user_dir / "conversations" / f"{conv_id}.json"
        self._write_json(path, conv)

        user_n = sum(1 for m in ft["messages"] if m["role"] == "user")
        asst_n = sum(1 for m in ft["messages"] if m["role"] == "assistant")
        return {"conv_id": conv_id, "message_count": ft["message_count"],
                "user_count": user_n, "assistant_count": asst_n}

    def delete_conversation(self, conv_id: str, cascade: bool = True):
        """
        删除对话记录

        复用 diarygpt 的源—派生关系经验：删除源对话时，级联删除所有引用此对话的洞察卡和模式卡。

        Args:
            conv_id: 对话记录 ID
            cascade: 是否级联删除
        """
        if not _is_valid_conversation_id(conv_id):
            # 非法 ID（可能含路径遍历片段）一律拒绝，不触碰任何文件
            return
        path = self.user_dir / "conversations" / f"{conv_id}.json"
        if path.exists():
            self._move_to_deleted(path, "conversations")

        if cascade:
            # 级联删除所有引用此对话的洞察卡（全量扫描，不被分页截断）
            insights = self.list_insights(limit=FULL_SCAN_LIMIT)
            for insight in insights:
                source_convs = insight.get("source_conversation_ids", [])
                if conv_id in source_convs:
                    self.delete_insight(insight["id"], cascade=True)

            # 级联删除所有引用此对话的模式卡（全量扫描）
            patterns = self.list_patterns(limit=FULL_SCAN_LIMIT)
            for pattern in patterns:
                source_convs = pattern.get("source_conversation_ids", [])
                if conv_id in source_convs:
                    self.delete_pattern(pattern["id"], cascade=True)

    # ============================================================
    # 模式卡
    # ============================================================

    def append_pattern(self, pattern: Dict) -> str:
        """追加模式卡"""
        pattern_id = pattern.get("id", self._generate_id("pattern"))
        pattern["id"] = pattern_id
        pattern["type"] = "pattern"
        pattern["created_at"] = pattern.get("created_at", self._now())
        pattern["updated_at"] = self._now()
        pattern["deleted"] = False
        pattern["deleted_at"] = None

        path = self.user_dir / "patterns" / f"{pattern_id}.json"
        self._write_json(path, pattern)
        return pattern_id

    def write_pattern(self, pattern: Dict):
        """写入模式卡（更新）"""
        pattern["updated_at"] = self._now()
        path = self.user_dir / "patterns" / f"{pattern['id']}.json"
        self._write_json(path, pattern)

    def list_patterns(self, limit: int = 20) -> List[Dict]:
        """列出模式卡"""
        patterns_dir = self.user_dir / "patterns"
        patterns = []
        for f in patterns_dir.glob("*.json"):
            data = self._read_json(f)
            if data and not data.get("deleted", False):
                patterns.append(data)
        patterns.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return patterns[:limit]

    def get_pattern(self, pattern_id: str) -> Optional[Dict]:
        """获取单个模式卡"""
        path = self.user_dir / "patterns" / f"{pattern_id}.json"
        data = self._read_json(path)
        if data and not data.get("deleted", False):
            return data
        return None

    def delete_pattern(self, pattern_id: str, cascade: bool = True):
        """
        删除模式卡

        Args:
            pattern_id: 模式卡 ID
            cascade: 是否级联处理（从回顾报告中移除引用）
        """
        path = self.user_dir / "patterns" / f"{pattern_id}.json"
        if path.exists():
            self._move_to_deleted(path, "patterns")

        if cascade:
            # 从回顾报告中移除对此模式卡的引用
            reviews = self.list_reviews()
            for review in reviews:
                patterns_to_review = review.get("patterns_to_review", [])
                patterns_to_review = [
                    p for p in patterns_to_review
                    if p.get("pattern_id") != pattern_id
                ]
                review["patterns_to_review"] = patterns_to_review
                self.save_review(review)

    # ============================================================
    # 回顾报告
    # ============================================================

    def save_review(self, report: Dict) -> str:
        """保存回顾报告"""
        review_id = report.get("id", self._generate_id("review"))
        report["id"] = review_id
        report["type"] = "review"
        report["created_at"] = report.get("created_at", self._now())
        report["updated_at"] = self._now()
        report["deleted"] = False
        report["deleted_at"] = None

        path = self.user_dir / "reviews" / f"{review_id}.json"
        self._write_json(path, report)
        return review_id

    def list_reviews(self, limit: int = 20) -> List[Dict]:
        """列出回顾报告"""
        reviews_dir = self.user_dir / "reviews"
        reviews = []
        for f in reviews_dir.glob("*.json"):
            data = self._read_json(f)
            if data and not data.get("deleted", False):
                reviews.append(data)
        reviews.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return reviews[:limit]

    def get_review(self, review_id: str) -> Optional[Dict]:
        """获取单个回顾报告"""
        path = self.user_dir / "reviews" / f"{review_id}.json"
        data = self._read_json(path)
        if data and not data.get("deleted", False):
            return data
        return None

    def delete_review(self, review_id: str):
        """删除回顾报告"""
        path = self.user_dir / "reviews" / f"{review_id}.json"
        if path.exists():
            self._move_to_deleted(path, "reviews")

    # ============================================================
    # 用户配置（复用 know-yourself 的配置.json 模块开关经验）
    # ============================================================

    def read_config(self) -> Dict:
        """
        读取用户配置

        Returns:
            用户配置数据，如果不存在则返回默认配置
        """
        path = self.user_dir / "config.json"
        data = self._read_json(path)
        if data is None:
            # 返回默认配置
            data = {
                "id": self._generate_id("config"),
                "type": "config",
                "version": 1,
                "created_at": self._now(),
                "updated_at": self._now(),
                "modules": {
                    "auto_archive_update": {
                        "enabled": True,
                        "description": "自动档案更新：每次对话结束后提炼洞察候选，用户确认后写入档案",
                        "updated_at": self._now(),
                    },
                    "pattern_recognition": {
                        "enabled": True,
                        "description": "跨时间模式识别：基于持久化档案识别重复模式",
                        "updated_at": self._now(),
                    },
                    "periodic_review": {
                        "enabled": True,
                        "description": "定期校准回顾：10次对话或1个月后邀请回顾",
                        "updated_at": self._now(),
                    },
                    "profile_driven_dialogue": {
                        "enabled": True,
                        "description": "画像驱动对话：基于生活风格画像提供个性化回应",
                        "updated_at": self._now(),
                    },
                },
                "preferences": {
                    "response_style": "direct",
                    "exploration_depth": "moderate",
                    "auto_invite_review": True,
                },
            }
            self._write_json(path, data)
        return data

    def write_config(self, config: Dict):
        """写入用户配置"""
        config["updated_at"] = self._now()
        config["version"] = config.get("version", 1) + 1
        path = self.user_dir / "config.json"
        self._write_json(path, config)

    def update_module(self, module_name: str, enabled: bool):
        """
        更新模块开关

        Args:
            module_name: 模块名称（auto_archive_update / pattern_recognition / periodic_review / profile_driven_dialogue）
            enabled: 是否启用
        """
        config = self.read_config()
        modules = config.get("modules", {})
        if module_name in modules:
            modules[module_name]["enabled"] = enabled
            modules[module_name]["updated_at"] = self._now()
            config["modules"] = modules
            self.write_config(config)

    def is_module_enabled(self, module_name: str) -> bool:
        """检查模块是否启用"""
        config = self.read_config()
        return config.get("modules", {}).get(module_name, {}).get("enabled", False)

    # ============================================================
    # 探索进度（复用 know-yourself 的进度保存经验）
    # ============================================================

    def read_progress(self) -> Optional[Dict]:
        """
        读取当前探索进度

        Returns:
            探索进度数据，如果不存在则返回 None
        """
        path = self.user_dir / "progress.json"
        return self._read_json(path)

    def write_progress(self, progress: Dict):
        """写入探索进度"""
        progress["updated_at"] = self._now()
        progress["last_active_at"] = self._now()
        path = self.user_dir / "progress.json"
        self._write_json(path, progress)

    def clear_progress(self):
        """清除探索进度"""
        path = self.user_dir / "progress.json"
        if path.exists():
            self._move_to_deleted(path, "")

    def can_resume(self) -> bool:
        """检查是否可以恢复之前的探索"""
        progress = self.read_progress()
        if progress is None:
            return False
        return progress.get("can_resume", False)

    # ============================================================
    # 全量删除
    # ============================================================

    def delete_all(self):
        """
        删除所有数据（级联删除）

        复用 diarygpt 的删除失效经验：删除后记录不可通过检索或模式证据访问。
        """
        # 删除所有洞察卡
        insights = self.list_insights(limit=FULL_SCAN_LIMIT)
        for insight in insights:
            self.delete_insight(insight["id"], cascade=False)

        # 删除所有对话记录
        conversations = self.list_conversations(limit=FULL_SCAN_LIMIT)
        for conv in conversations:
            self.delete_conversation(conv["id"], cascade=False)

        # 删除所有模式卡
        patterns = self.list_patterns(limit=FULL_SCAN_LIMIT)
        for pattern in patterns:
            self.delete_pattern(pattern["id"], cascade=False)

        # 删除所有回顾报告
        reviews = self.list_reviews(limit=FULL_SCAN_LIMIT)
        for review in reviews:
            self.delete_review(review["id"])

        # 删除画像（全量版和精简版）
        for filename in ["profile.json", "profile.lite.json"]:
            path = self.user_dir / filename
            if path.exists():
                self._move_to_deleted(path, "")

        # 删除配置
        path = self.user_dir / "config.json"
        if path.exists():
            self._move_to_deleted(path, "")

        # 清除进度
        self.clear_progress()

    # ============================================================
    # 统计信息
    # ============================================================

    def get_stats(self) -> Dict:
        """获取存储统计信息"""
        return {
            "storage_mode": self.get_storage_mode(),
            "user_id": self.user_id,
            "insights_count": len(self.list_insights(limit=FULL_SCAN_LIMIT)),
            "conversations_count": len(self.list_conversations(limit=FULL_SCAN_LIMIT)),
            "patterns_count": len(self.list_patterns(limit=FULL_SCAN_LIMIT)),
            "reviews_count": len(self.list_reviews(limit=FULL_SCAN_LIMIT)),
            "profile_exists": (self.user_dir / "profile.json").exists(),
            "config_exists": (self.user_dir / "config.json").exists(),
            "progress_exists": (self.user_dir / "progress.json").exists(),
        }


# ============================================================
# 便捷函数
# ============================================================

def create_storage(user_id: str = "default", base_dir: str = "storage/data") -> LocalJsonStorageAdapter:
    """
    创建存储适配器实例

    Args:
        user_id: 用户 ID
        base_dir: 基础目录

    Returns:
        LocalJsonStorageAdapter 实例
    """
    return LocalJsonStorageAdapter(base_dir=base_dir, user_id=user_id)


if __name__ == "__main__":
    # 简单测试
    storage = create_storage(user_id="test_user")
    print("存储模式:", storage.get_storage_mode())
    print("存储能力:", storage.get_storage_capabilities())
    print("统计信息:", storage.get_stats())
