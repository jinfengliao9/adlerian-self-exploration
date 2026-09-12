#!/usr/bin/env python3
"""
官方删除脚本：删除对话记录（含级联删除相关洞察卡和模式卡）

【为什么需要这个脚本】
  之前 agent 自己写临时删除脚本时，容易犯路径错误（parents[1] 指错目录）、
  缺少回读验证等问题，导致删除操作显示成功但实际没有删除，档案中出现重复对话。
  这个官方脚本统一了删除操作，使用基于脚本自身位置的绝对路径，删除后强制回读验证。

【严禁】
  - 严禁自己写临时脚本代替这个官方删除脚本
  - 严禁在 skill 根目录创建可执行 Python 脚本（所有正式脚本都在 scripts/ 下）
  - 严禁删除后不回读验证就说"删除成功"

使用方式：
  # 列出所有对话记录（不删除，用于查看）
  python scripts/delete_conversation.py --list

  # 删除指定对话记录（需要确认）
  python scripts/delete_conversation.py --id <对话记录ID>

  # 删除指定对话记录（强制删除，不需要确认，用于自动化场景）
  python scripts/delete_conversation.py --id <对话记录ID> --force

  # 加密存储（密码通过环境变量传递）
  $env:ADLERIAN_PASSWORD="<密码>"; python scripts/delete_conversation.py --list --storage-mode local_encrypted

参数说明：
  --list: 列出所有对话记录（不删除）
  --id: 要删除的对话记录 ID
  --force: 强制删除，不需要确认（默认需要确认）
  --storage-mode: local_unencrypted（默认）或 local_encrypted

环境变量：
  ADLERIAN_PASSWORD: 加密存储的密码（仅当使用加密存储时需要）

删除级联规则：
  删除对话记录时，会自动级联删除：
  - 关联的洞察卡（source_conversation_ids 包含该对话 ID 的洞察卡）
  - 关联的模式卡（source_conversation_ids 包含该对话 ID 的模式卡）
  - 重新评估剩余洞察卡是否还能支撑模式卡的证据门槛
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

from storage.adapters.local_json import LocalJsonStorageAdapter, _is_valid_conversation_id
from storage.adapters.local_encrypted import LocalEncryptedStorageAdapter

# 固定的数据存储目录（绝对路径）
DATA_DIR = str(PROJECT_ROOT / "storage" / "data")
USER_ID = "default"


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


def list_conversations(storage):
    """列出所有对话记录"""
    conversations = storage.list_conversations()
    if not conversations:
        print("当前没有对话记录。")
        return

    print("=" * 70)
    print(f"对话记录列表（共 {len(conversations)} 条）")
    print("=" * 70)
    for i, conv in enumerate(conversations, 1):
        conv_id = conv.get("id", "未知")
        summary = conv.get("summary", "（无摘要）")[:60]
        conv_type = conv.get("conversation_type", "未知")
        created_at = conv.get("created_at", "未知")
        msg_count = conv.get("full_transcript", {}).get("message_count", 0)
        related_insights = conv.get("related_insights", [])

        print(f"\n[{i}] ID: {conv_id}")
        print(f"    类型: {conv_type}")
        print(f"    摘要: {summary}")
        print(f"    创建时间: {created_at}")
        print(f"    消息数: {msg_count}")
        print(f"    关联洞察卡: {len(related_insights)} 条")

    print("\n" + "=" * 70)
    print("使用 --id <对话记录ID> 删除指定对话记录")
    print("=" * 70)


def delete_conversation(storage, conv_id, force=False):
    """删除指定对话记录，删除后强制回读验证"""
    # 先检查对话记录是否存在
    conversation = storage.get_conversation(conv_id)
    if not conversation:
        print(f"❌ 错误：对话记录不存在: {conv_id}")
        sys.exit(1)

    # 显示要删除的内容
    print("=" * 70)
    print("即将删除以下对话记录：")
    print("=" * 70)
    print(f"  ID: {conv_id}")
    print(f"  类型: {conversation.get('conversation_type', '未知')}")
    print(f"  摘要: {conversation.get('summary', '（无摘要）')[:80]}")
    print(f"  创建时间: {conversation.get('created_at', '未知')}")
    print(f"  消息数: {conversation.get('full_transcript', {}).get('message_count', 0)}")
    print(f"  关联洞察卡: {len(conversation.get('related_insights', []))} 条")
    print()
    print("⚠️  删除级联：删除对话记录时，会自动级联删除：")
    print("    - 关联的洞察卡（source_conversation_ids 包含该对话 ID）")
    print("    - 关联的模式卡（source_conversation_ids 包含该对话 ID）")
    print("=" * 70)

    # 确认删除
    if not force:
        confirm = input("\n确认删除？输入 'yes' 确认，其他输入取消: ").strip().lower()
        if confirm != 'yes':
            print("已取消删除。")
            return

    # 执行删除
    print("\n正在删除...")
    storage.delete_conversation(conv_id)

    # 强制回读验证
    verify = storage.get_conversation(conv_id)
    if verify:
        print(f"❌ 错误：删除后回读验证失败，对话 ID {conv_id} 仍然存在")
        sys.exit(1)

    print(f"✅ 删除成功：对话记录 {conv_id} 已删除（已回读验证）")

    # 显示删除后的状态
    remaining = storage.list_conversations()
    print(f"   当前剩余对话记录: {len(remaining)} 条")


def main():
    parser = argparse.ArgumentParser(
        description='官方删除脚本：删除对话记录（含级联删除，删除后强制回读验证）'
    )
    parser.add_argument('--list', action='store_true', help='列出所有对话记录（不删除）')
    parser.add_argument('--id', type=str, help='要删除的对话记录 ID')
    parser.add_argument('--force', action='store_true', help='强制删除，不需要确认')
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

    # 初始化存储
    storage = build_storage(args.storage_mode, password)

    if args.list:
        list_conversations(storage)
    elif args.id:
        # 对话 ID 严格格式校验，拒绝含 .. / 路径分隔符 / 绝对路径的非法 ID（防路径遍历）
        if not _is_valid_conversation_id(args.id):
            print("❌ 错误：对话记录 ID 格式非法，拒绝操作（应为 conversation-<12位十六进制>）")
            sys.exit(1)
        delete_conversation(storage, args.id, force=args.force)
    else:
        parser.print_help()
        print("\n示例：")
        print("  列出所有对话记录: python scripts/delete_conversation.py --list")
        print("  删除指定对话记录: python scripts/delete_conversation.py --id <对话记录ID>")
        sys.exit(1)


if __name__ == "__main__":
    main()
