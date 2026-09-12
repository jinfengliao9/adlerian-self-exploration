"""
初步画像保存脚本

用于将初步生活风格画像保存到本地存储。
支持未加密存储和加密存储。

安全说明：
  密码通过环境变量 ADLERIAN_PASSWORD 传递，严禁在命令行参数中明文传递密码。
  命令行参数中的密码会暴露在进程列表、终端历史和日志中，存在安全风险。

使用方式：
  # 未加密存储（仅画像）
  python scripts/save_profile.py --input <画像JSON文件路径>

  # 加密存储（通过环境变量传递密码）
  $env:ADLERIAN_PASSWORD="<密码>"; python scripts/save_profile.py --input <画像JSON> --storage-mode local_encrypted

  # 一次性串联保存【画像 + 完整对话原文】（推荐，避免两步脱节）
  python scripts/save_profile.py --input <画像JSON> --transcript-input <对话JSON>
  # 对话 JSON 的要求与 save_conversation.py 完全一致：必须带 transcript_source
  # （method=conversation_history）和每条消息的真实 timestamp，会先过五道硬校验再存画像。

参数说明：
  --input: 画像数据的 JSON 文件路径（必需）
  --transcript-input: 本次画像对应的完整对话 JSON 路径（可选）；提供时在同一次调用内
                      先校验并保存逐字对话原文、再保存画像，保证两者一起落库、不脱节
  --storage-mode: 存储模式，可选 local_unencrypted 或 local_encrypted（默认 local_unencrypted）

环境变量：
  ADLERIAN_PASSWORD: 加密存储的密码（仅当使用加密存储时需要）

输入的画像 JSON 格式：
{
  "confirmed_understandings": [...],  // 已确认的理解列表
  "pending_understandings": [...],    // 待验证的理解列表
  "confirmed_patterns": [...],         // 已确认的模式列表
  "strengths_and_values": {...},       // 优势和价值观
  "trigger_boundaries": {...},         // 触发边界和回应偏好
  "current_focus": {...}               // 当前关注
}

输出：
  - 保存成功时，输出保存结果摘要
  - 保存失败时，输出错误信息并返回非零退出码
"""

import sys
import os
import json
import argparse
from datetime import datetime
from pathlib import Path

# 添加项目根目录与 scripts 目录到路径
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from storage.adapters.local_json import LocalJsonStorageAdapter
from storage.adapters.local_encrypted import LocalEncryptedStorageAdapter
# 复用完整对话保存的全部校验逻辑（五道硬校验 + 来源凭证），不重复实现
import save_conversation as sc

# 固定的数据存储目录（绝对路径，不依赖运行脚本时的工作目录）
DATA_DIR = str(PROJECT_ROOT / "storage" / "data")
USER_ID = "default"


def load_profile_data(input_path):
    """加载画像数据从 JSON 文件"""
    if not os.path.exists(input_path):
        print(f"错误：输入文件不存在: {input_path}")
        sys.exit(1)

    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data
    except json.JSONDecodeError as e:
        print(f"错误：输入文件不是有效的 JSON: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"错误：读取输入文件失败: {e}")
        sys.exit(1)


def build_full_profile(profile_data):
    """构建完整的 profile 数据结构"""
    now = datetime.now().isoformat()

    profile = {
        "id": f"uuid-profile-{int(datetime.now().timestamp())}",
        "type": "profile",
        "version": 1,
        "created_at": now,
        "updated_at": now,
        "source": "initial-profile-building",
        "sensitivity_level": "medium",
        "deleted": False,
        "deleted_at": None,
        "profile_status": "initialized",  # 通过初步画像建立工作流系统建立，标记为已完成初步画像
        "current_focus": profile_data.get("current_focus", {}),
        "confirmed_understandings": profile_data.get("confirmed_understandings", []),
        "pending_understandings": profile_data.get("pending_understandings", []),
        "trigger_boundaries": profile_data.get("trigger_boundaries", {}),
        "strengths_and_values": profile_data.get("strengths_and_values", {}),
        "confirmed_patterns": profile_data.get("confirmed_patterns", []),
        "lifestyle_overview": profile_data.get("lifestyle_overview", {
            "core_summary": "",
            "key_themes": [],
            "confidence": "",
            "note": "",
            "created_at": now,
            "last_updated": now,
        }),
        "core_dimensions": profile_data.get("core_dimensions", {
            "self_concept": {
                "core_belief": "",
                "details": [],
                "source": "",
                "confidence": "",
                "user_correction": "",
                "last_updated": now,
            },
            "self_ideal": {
                "core_belief": "",
                "details": [],
                "source": "",
                "confidence": "",
                "user_correction": "",
                "last_updated": now,
            },
            "world_view": {
                "core_belief": "",
                "details": [],
                "source": "",
                "confidence": "",
                "user_correction": "",
                "last_updated": now,
            },
            "view_of_others": {
                "core_belief": "",
                "details": [],
                "source": "",
                "confidence": "",
                "user_correction": "",
                "last_updated": now,
            },
            "private_logic": {
                "core_belief": "",
                "details": [],
                "source": "",
                "confidence": "",
                "user_correction": "",
                "last_updated": now,
            },
            "basic_mistakes": {
                "core_belief": "",
                "details": [],
                "source": "",
                "confidence": "",
                "user_correction": "",
                "last_updated": now,
            },
            "behavioral_strategies": {
                "core_belief": "",
                "details": [],
                "source": "",
                "confidence": "",
                "user_correction": "",
                "last_updated": now,
            },
            "social_interest": {
                "core_belief": "",
                "details": [],
                "source": "",
                "confidence": "",
                "user_correction": "",
                "last_updated": now,
            },
            "inferiority_and_compensation": {
                "core_belief": "",
                "details": [],
                "source": "",
                "confidence": "",
                "user_correction": "",
                "last_updated": now,
            },
        }),
        "change_log": [
            {
                "id": f"change-{int(datetime.now().timestamp())}",
                "date": now[:10],
                "change_type": "add",
                "user_modification": "初步画像建立完成，保存完整画像",
                "processing_notes": "通过 save_profile.py 脚本保存"
            }
        ]
    }

    return profile


def build_storage(storage_mode, password=None):
    """创建并验证存储适配器（绝对路径固定落到本 Skill 目录）"""
    if storage_mode == "local_encrypted":
        if not password:
            print("错误：使用加密存储时必须提供密码")
            sys.exit(1)
        storage = LocalEncryptedStorageAdapter(
            base_dir=DATA_DIR, user_id=USER_ID, password=password
        )
        if not storage.verify_password(password):
            print("错误：密码验证失败")
            sys.exit(1)
    else:
        storage = LocalJsonStorageAdapter(base_dir=DATA_DIR, user_id=USER_ID)
    return storage


def save_transcript_alongside(transcript_path, storage):
    """在保存画像前，先把本次完整对话原文校验并保存（复用 save_conversation 的五道硬校验）。
    返回对话记录 ID。"""
    data, messages = sc.load_messages(transcript_path)
    src_errors, source = sc.validate_source(data)
    if src_errors:
        print("❌ 完整对话来源校验未通过，已中止（画像也不会保存）：")
        for e in src_errors:
            print(f"  - {e}")
        sys.exit(1)
    # create_conversation 内部会做五道形式/时间戳校验，不过则非零退出
    conv_id, _saved = sc.create_conversation(data, messages, storage, source)
    return conv_id


def write_and_verify_profile(profile, storage):
    """写入画像并回读验证"""
    try:
        storage.write_profile(profile)
        saved_profile = storage.read_profile()
        if not saved_profile:
            print("错误：保存后读取画像失败")
            sys.exit(1)
        return saved_profile
    except SystemExit:
        raise
    except Exception as e:
        print(f"错误：保存画像失败: {e}")
        sys.exit(1)


def print_save_summary(saved_profile):
    """打印保存结果摘要"""
    print("=" * 60)
    print("画像保存成功")
    print("=" * 60)
    print()

    print(f"画像ID: {saved_profile.get('id')}")
    print(f"画像版本: {saved_profile.get('version')}")
    print(f"保存时间: {saved_profile.get('updated_at')}")
    print()

    confirmed = saved_profile.get('confirmed_understandings', [])
    pending = saved_profile.get('pending_understandings', [])
    patterns = saved_profile.get('confirmed_patterns', [])

    print(f"已确认的理解: {len(confirmed)} 条")
    for i, item in enumerate(confirmed, 1):
        title = item.get('title', item.get('id', f'理解{i}'))
        print(f"  {i}. {title}")
    print()

    print(f"待验证的理解: {len(pending)} 条")
    for i, item in enumerate(pending, 1):
        title = item.get('title', item.get('id', f'待验证{i}'))
        print(f"  {i}. {title}")
    print()

    print(f"已确认的模式: {len(patterns)} 个")
    for i, pattern in enumerate(patterns, 1):
        desc = pattern.get('description', pattern.get('id', f'模式{i}'))
        if len(desc) > 60:
            desc = desc[:60] + "..."
        print(f"  {i}. {desc}")
    print()

    strengths = saved_profile.get('strengths_and_values', {})
    if strengths:
        print("优势和价值观: 已保存")
    print()

    print("=" * 60)
    print("保存完成")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description='保存初步生活风格画像（可一次性串联保存完整对话原文）')
    parser.add_argument('--input', required=True, help='画像数据的 JSON 文件路径')
    parser.add_argument('--transcript-input', default=None,
                        help='本次画像对应的完整对话 JSON 路径；提供时先校验保存逐字对话、再保存画像')
    parser.add_argument('--storage-mode', default='local_unencrypted',
                        choices=['local_unencrypted', 'local_encrypted'],
                        help='存储模式（默认 local_unencrypted）')

    args = parser.parse_args()

    # 从环境变量读取密码（安全方式，避免命令行参数暴露密码）
    password = os.environ.get('ADLERIAN_PASSWORD')

    # 如果使用加密存储但环境变量中没有密码，报错退出
    if args.storage_mode == 'local_encrypted' and not password:
        print("错误：使用加密存储时必须通过环境变量 ADLERIAN_PASSWORD 提供密码")
        print("安全提示：严禁在命令行参数中明文传递密码，应使用环境变量传递")
        sys.exit(1)

    # 加载画像数据并构建完整结构
    profile_data = load_profile_data(args.input)
    profile = build_full_profile(profile_data)

    # 创建同一个存储适配器，保证对话与画像落到同一用户目录
    storage = build_storage(args.storage_mode, password)

    # 若提供了完整对话，先校验并保存对话（校验不过会直接中止，画像也不会写）
    conv_id = None
    if args.transcript_input:
        print("先保存本次完整对话原文（五道硬校验）……")
        conv_id = save_transcript_alongside(args.transcript_input, storage)
        print(f"完整对话已保存：{conv_id}\n")

    # 再保存画像并回读验证
    saved_profile = write_and_verify_profile(profile, storage)

    # 合并之前的零散洞察：如果用户在建立初步画像之前已经进行过探索性对话并保存了洞察，
    # 这些洞察卡是独立存储的，不会被新画像覆盖。建立完整画像后，自动将这些已确认的洞察
    # 重新累积到新画像的 core_dimensions.details 中，确保之前的理解不丢失。
    try:
        all_insights = storage.list_insights()
        confirmed_insights = [i for i in all_insights if i.get("user_confirmed", False)]
        if confirmed_insights:
            print(f"\n检测到之前保存的 {len(confirmed_insights)} 条已确认洞察，正在合并到新画像中……")
            merged_count = 0
            for insight in confirmed_insights:
                result = storage.accumulate_insight_to_profile(insight)
                if result.get("details_added", 0) > 0:
                    merged_count += 1
            print(f"已将 {merged_count} 条洞察的新细节合并到画像对应维度（之前的零散理解不会丢失）。")
    except Exception as e:
        # 合并失败不影响画像保存，只是打印提示
        print(f"\n提示：合并之前的零散洞察时出现问题（不影响画像保存）：{e}")
        print("之前的洞察卡仍然保留，你可以后续手动触发合并。")

    # 打印保存结果摘要
    print_save_summary(saved_profile)
    if conv_id:
        print(f"本次完整对话记录已一并保存：{conv_id}")


if __name__ == "__main__":
    main()
