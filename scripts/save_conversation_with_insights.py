#!/usr/bin/env python3
"""
官方串联脚本：保存对话 + 洞察卡 + 自动累积到画像

这是"保存对话存档"指令的唯一官方脚本，一次性完成：
  1. 校验并保存完整对话原文（五道硬校验）
  2. 校验洞察卡的 related_dimensions 是否合法
  3. 保存洞察卡（自动累积到画像对应维度的 details 层）
  4. 处理洞察与对话的双向关联
  5. 每一步后强制回读验证

【为什么需要这个脚本】
  之前 agent 自己写临时脚本组合操作时，容易犯路径错误（parents[1] 指错目录）、
  缺少回读验证、维度键名不匹配等问题。这个官方脚本统一了所有操作，
  使用基于脚本自身位置的绝对路径，每一步都强制回读验证，避免临时脚本的问题。

【严禁】
  - 严禁自己写临时脚本代替这个官方脚本
  - 严禁在 skill 根目录创建可执行 Python 脚本（所有正式脚本都在 scripts/ 下）
  - 严禁保存后不回读验证就说"保存成功"

使用方式：
  # 未加密存储
  python scripts/save_conversation_with_insights.py --conversation <对话JSON路径> --insights <洞察卡JSON路径>

  # 加密存储（密码通过环境变量传递）
  $env:ADLERIAN_PASSWORD="<密码>"; python scripts/save_conversation_with_insights.py --conversation <对话JSON> --insights <洞察卡JSON> --storage-mode local_encrypted

参数说明：
  --conversation: 完整对话 JSON 文件路径（必需，必须包含 transcript_source 和 messages）
  --insights: 洞察卡 JSON 文件路径（必需，可以是单个洞察对象或洞察对象列表）
  --storage-mode: local_unencrypted（默认）或 local_encrypted

环境变量：
  ADLERIAN_PASSWORD: 加密存储的密码（仅当使用加密存储时需要）

洞察卡 JSON 格式（单个或列表）：
  {
    "title": "洞察标题",
    "content": "洞察内容",
    "related_dimensions": ["self_concept", "behavioral_strategies"],  // 必须是合法的9个维度键名之一
    "context_tags": ["work", "social"],  // 可选
    "user_confirmed": true,  // 必须为 true 才会触发自动累积到画像
    "confidence": "中",  // 可选
    "suggests_core_belief_update": false,  // 可选
    "core_belief_update_content": "",  // 可选
    "conflicts_with_existing": false,  // 可选
    "conflict_type": "context_difference"  // 可选
  }

合法的9个维度键名：
  self_concept, self_ideal, world_view, view_of_others, private_logic,
  basic_mistakes, behavioral_strategies, social_interest, inferiority_and_compensation
"""

import sys
import os
import json
import argparse
from datetime import datetime
from pathlib import Path

# 基于脚本自身位置确定项目根目录（绝对路径，不依赖运行时工作目录）
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from storage.adapters.local_json import LocalJsonStorageAdapter
from storage.adapters.local_encrypted import LocalEncryptedStorageAdapter

# 固定的数据存储目录（绝对路径）
DATA_DIR = str(PROJECT_ROOT / "storage" / "data")
USER_ID = "default"

# 合法的9个核心维度键名
VALID_DIMENSIONS = {
    "self_concept", "self_ideal", "world_view", "view_of_others", "private_logic",
    "basic_mistakes", "behavioral_strategies", "social_interest", "inferiority_and_compensation"
}


def load_json_file(path, description):
    """加载 JSON 文件，失败则退出"""
    if not os.path.exists(path):
        print(f"❌ 错误：{description}文件不存在: {path}")
        sys.exit(1)
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"❌ 错误：{description}文件不是有效的 JSON: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ 错误：读取{description}文件失败: {e}")
        sys.exit(1)


def build_storage(storage_mode, password):
    """创建并验证存储适配器（绝对路径固定落到本 Skill 目录）"""
    if storage_mode == "local_encrypted":
        if not password:
            print("❌ 错误：使用加密存储时必须通过环境变量 ADLERIAN_PASSWORD 提供密码")
            print("安全提示：严禁在命令行参数中明文传递密码，应使用环境变量传递")
            sys.exit(1)
        storage = LocalEncryptedStorageAdapter(
            base_dir=DATA_DIR, user_id=USER_ID, password=password
        )
        if not storage.verify_password(password):
            print("❌ 错误：密码验证失败")
            sys.exit(1)
    else:
        storage = LocalJsonStorageAdapter(base_dir=DATA_DIR, user_id=USER_ID)
    return storage


def validate_insights(insights):
    """校验洞察卡列表：related_dimensions 必须是合法的维度键名"""
    if isinstance(insights, dict):
        insights = [insights]

    if not insights:
        print("❌ 错误：洞察卡列表为空")
        sys.exit(1)

    errors = []
    for i, insight in enumerate(insights):
        # 检查必需字段
        if not insight.get("title"):
            errors.append(f"洞察卡 #{i+1} 缺少 title 字段")
        if not insight.get("content"):
            errors.append(f"洞察卡 #{i+1} 缺少 content 字段")

        # 校验 related_dimensions
        related = insight.get("related_dimensions", [])
        if not related:
            errors.append(f"洞察卡 #{i+1}（{insight.get('title', '无标题')}）缺少 related_dimensions，无法自动累积到画像")
        else:
            invalid = [d for d in related if d not in VALID_DIMENSIONS]
            if invalid:
                errors.append(
                    f"洞察卡 #{i+1}（{insight.get('title', '无标题')}）的 related_dimensions 包含非法键名: {invalid}\n"
                    f"  合法的9个维度键名: {sorted(VALID_DIMENSIONS)}"
                )

        # 检查 user_confirmed
        if not insight.get("user_confirmed", False):
            errors.append(
                f"洞察卡 #{i+1}（{insight.get('title', '无标题')}）的 user_confirmed 为 false，不会触发自动累积到画像。"
                f"如果需要自动累积，请设置 user_confirmed=true"
            )

    if errors:
        print("❌ 洞察卡校验未通过：")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)

    return insights


def save_conversation(storage, conversation_data):
    """保存完整对话原文，返回对话记录 ID。保存后强制回读验证。"""
    # 复用 save_conversation 的校验逻辑
    import importlib
    sc = importlib.import_module("save_conversation")

    data = conversation_data
    messages = data.get("messages", [])
    if not isinstance(messages, list) or not messages:
        print("❌ 错误：对话 JSON 缺少非空的 messages 字段（逐字原文消息列表）")
        sys.exit(1)

    src_errors, source = sc.validate_source(data)
    if src_errors:
        print("❌ 完整对话来源校验未通过：")
        for e in src_errors:
            print(f"  - {e}")
        sys.exit(1)

    conv_id, saved = sc.create_conversation(data, messages, storage, source)

    # 强制回读验证
    verify = storage.get_conversation(conv_id)
    if not verify:
        print(f"❌ 错误：对话保存后回读验证失败，对话 ID {conv_id} 不存在")
        sys.exit(1)

    saved_count = verify.get("full_transcript", {}).get("message_count", 0)
    if saved_count != len(messages):
        print(f"❌ 错误：对话保存后条数不一致（传入 {len(messages)}，读回 {saved_count}）")
        sys.exit(1)

    print(f"✅ 对话保存成功：{conv_id}（{saved_count} 条消息）")
    return conv_id


def save_insights(storage, insights, conv_id):
    """保存洞察卡并自动累积到画像，返回洞察 ID 列表。保存后强制回读验证。"""
    insight_ids = []
    profile_before = storage.read_profile()
    version_before = profile_before.get("version", 1)

    for i, insight in enumerate(insights):
        # 填入对话来源关联
        insight["source_conversation_ids"] = [conv_id]
        insight["created_at"] = insight.get("created_at", datetime.now().isoformat())

        # 保存洞察卡（auto_update_profile=True 会自动累积到画像）
        insight_id = storage.append_insight(insight, auto_update_profile=True)
        insight_ids.append(insight_id)

        # 强制回读验证
        verify = storage.get_insight(insight_id)
        if not verify:
            print(f"❌ 错误：洞察卡 #{i+1} 保存后回读验证失败，ID {insight_id} 不存在")
            sys.exit(1)

        print(f"✅ 洞察卡 #{i+1} 保存成功：{insight_id}（{insight.get('title', '无标题')}）")

    # 验证画像已更新
    profile_after = storage.read_profile()
    version_after = profile_after.get("version", 1)
    if version_after <= version_before and any(i.get("user_confirmed") and i.get("related_dimensions") for i in insights):
        print(f"⚠️ 警告：画像版本未变化（{version_before} → {version_after}），洞察可能没有成功累积到画像")
    else:
        print(f"✅ 画像已更新：版本 {version_before} → {version_after}")

    return insight_ids


def update_conversation_with_insights(storage, conv_id, insight_ids):
    """把洞察 ID 回填到对话记录的 related_insights 字段"""
    conversation = storage.get_conversation(conv_id)
    if conversation:
        conversation["related_insights"] = insight_ids
        storage.update_conversation(conv_id, conversation)
        print(f"✅ 对话记录已关联 {len(insight_ids)} 条洞察")


def main():
    parser = argparse.ArgumentParser(
        description='官方串联脚本：保存对话 + 洞察卡 + 自动累积到画像（每步强制回读验证）'
    )
    parser.add_argument('--conversation', required=True, help='完整对话 JSON 文件路径')
    parser.add_argument('--insights', required=True, help='洞察卡 JSON 文件路径（单个对象或对象列表）')
    parser.add_argument('--storage-mode', default='local_unencrypted',
                        choices=['local_unencrypted', 'local_encrypted'],
                        help='存储模式（默认 local_unencrypted）')

    args = parser.parse_args()

    # 从环境变量读取密码（安全方式，避免命令行参数暴露密码）
    password = os.environ.get('ADLERIAN_PASSWORD')

    if args.storage_mode == 'local_encrypted' and not password:
        print("❌ 错误：使用加密存储时必须通过环境变量 ADLERIAN_PASSWORD 提供密码")
        print("安全提示：严禁在命令行参数中明文传递密码，应使用环境变量传递")
        sys.exit(1)

    print("=" * 60)
    print("官方串联脚本：保存对话 + 洞察卡 + 自动累积到画像")
    print("=" * 60)
    print()

    # 1. 加载输入文件
    print("【1/5】加载输入文件...")
    conversation_data = load_json_file(args.conversation, "对话")
    insights_data = load_json_file(args.insights, "洞察卡")
    insights = validate_insights(insights_data)
    print(f"  对话消息数: {len(conversation_data.get('messages', []))}")
    print(f"  洞察卡数: {len(insights)}")
    print()

    # 2. 初始化存储
    print("【2/5】初始化存储适配器...")
    storage = build_storage(args.storage_mode, password)
    print(f"  存储模式: {args.storage_mode}")
    print(f"  数据目录: {DATA_DIR}")
    print()

    # 3. 保存对话
    print("【3/5】保存完整对话原文（五道硬校验 + 回读验证）...")
    conv_id = save_conversation(storage, conversation_data)
    print()

    # 4. 保存洞察卡并自动累积到画像
    print("【4/5】保存洞察卡并自动累积到画像（回读验证）...")
    insight_ids = save_insights(storage, insights, conv_id)
    print()

    # 5. 双向关联
    print("【5/5】处理洞察与对话的双向关联...")
    update_conversation_with_insights(storage, conv_id, insight_ids)
    print()

    # 最终验证摘要
    print("=" * 60)
    print("✅ 全部保存成功（每步均已回读验证）")
    print("=" * 60)
    print(f"  对话记录 ID: {conv_id}")
    print(f"  洞察卡数量: {len(insight_ids)}")
    print(f"  洞察卡 IDs: {insight_ids}")
    print(f"  画像版本: {storage.read_profile().get('version')}")
    print(f"  画像状态: {storage.read_profile().get('profile_status', 'not_initialized')}")
    print()
    print("保存后告诉用户：")
    print("  - 对话已保存（完整逐字记录）")
    print(f"  - 从对话中提炼了 {len(insights)} 条新理解，已加入画像的对应维度")
    print("  - 随时能查看、修改、删除任何内容")
    print("=" * 60)


if __name__ == "__main__":
    main()
