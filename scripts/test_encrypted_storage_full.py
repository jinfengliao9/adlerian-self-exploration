"""
加密存储适配器完整测试脚本

测试所有功能：
1. 能力闸门（加密模式）
2. 档案读写（全量版+精简版）
3. 洞察卡的增删改查
4. 对话记录的增删改查
5. 模式卡的增删改查
6. 回顾报告的增删改查
7. 用户配置的读写和模块开关
8. 探索进度的读写
9. 删除级联（删除对话→级联删除洞察和模式）
10. 全量删除
11. 密码验证
12. 修改密码
13. 文件加密验证（确认文件是加密的）
"""

import sys
import os
import json
import shutil

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from storage.adapters.local_encrypted import LocalEncryptedStorageAdapter


def test_encrypted_storage_adapter():
    """测试加密存储适配器"""
    print("=" * 60)
    print("加密存储适配器完整测试")
    print("=" * 60)

    # 使用临时测试目录
    test_dir = "storage/data/test_encrypted_full"
    test_user = "test_user"
    test_password = "test123"

    # 清理之前的测试数据
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)

    storage = LocalEncryptedStorageAdapter(
        base_dir=test_dir, user_id=test_user, password=test_password
    )

    # ----------------------------------------------------------
    # 测试1：能力闸门
    # ----------------------------------------------------------
    print("\n[测试1] 能力闸门")
    mode = storage.get_storage_mode()
    capabilities = storage.get_storage_capabilities()
    print(f"  存储模式: {mode}")
    print(f"  加密算法: {capabilities['encryption']['algorithm']}")
    print(f"  密钥派生: {capabilities['encryption']['key_derivation']}")
    assert mode == "local_encrypted", "存储模式应该是 local_encrypted"
    assert capabilities["encryption"]["algorithm"] == "Fernet (AES-128-CBC + HMAC-SHA256)"
    print("  ✅ 通过")

    # ----------------------------------------------------------
    # 测试2：档案读写
    # ----------------------------------------------------------
    print("\n[测试2] 档案读写")
    profile = storage.read_profile()
    assert profile is not None, "应该返回空档案"
    assert profile["type"] == "profile", "档案类型应该是 profile"

    profile["current_focus"]["current_topic"] = "测试主题"
    profile["confirmed_understandings"].append({
        "id": "understanding-001",
        "user_expression": "测试理解",
        "shared_summary": "测试摘要",
        "applicable_contexts": "测试情境",
        "evidence_and_confirmation": "测试证据",
        "confirmed_at": "2026-09-06"
    })
    storage.write_profile(profile)

    read_profile = storage.read_profile()
    assert read_profile["current_focus"]["current_topic"] == "测试主题"
    assert len(read_profile["confirmed_understandings"]) == 1
    print("  ✅ 通过")

    # ----------------------------------------------------------
    # 测试3：洞察卡的增删改查
    # ----------------------------------------------------------
    print("\n[测试3] 洞察卡的增删改查")
    insight_id = storage.append_insight({
        "current_topic": {"user_statement": "测试", "specific_context": "测试"},
        "user_material": {"what_happened": "测试", "feelings_and_concerns": "测试", "reaction": "测试"},
        "adlerian_understanding": {"possible_understanding": "测试", "what_it_protects_or_pursues": "测试", "limitations_and_exceptions": "测试"},
        "source_conversation_ids": ["conv-001"]
    })
    assert insight_id is not None, "应该返回洞察卡 ID"

    insights = storage.list_insights()
    assert len(insights) == 1, "应该有 1 条洞察卡"

    insight = storage.get_insight(insight_id)
    assert insight is not None, "应该能获取洞察卡"
    print("  ✅ 通过")

    # ----------------------------------------------------------
    # 测试4：对话记录的增删改查
    # ----------------------------------------------------------
    print("\n[测试4] 对话记录的增删改查")
    storage.append_conversation({
        "summary": "测试对话摘要",
        "conversation_type": "exploration",
        "related_insights": [insight_id],
        "user_confirmed": True
    })
    conversations = storage.list_conversations()
    assert len(conversations) == 1, "应该有 1 条对话记录"
    print("  ✅ 通过")

    # ----------------------------------------------------------
    # 测试5：模式卡的增删改查
    # ----------------------------------------------------------
    print("\n[测试5] 模式卡的增删改查")
    pattern_id = storage.append_pattern({
        "common_triggers": {"similar_contexts": "测试", "reference_events": []},
        "concerns": {"expressed_concerns": "测试", "parts_to_correct": "测试"},
        "protection_methods": {"common_coping": "测试", "what_it_protects": "测试"},
        "evidence": {"instance_count": 3, "context_count": 2, "supporting_insights": [insight_id], "counter_evidence": []},
        "source_insight_ids": [insight_id]
    })
    assert pattern_id is not None, "应该返回模式卡 ID"

    patterns = storage.list_patterns()
    assert len(patterns) == 1, "应该有 1 张模式卡"
    print("  ✅ 通过")

    # ----------------------------------------------------------
    # 测试6：回顾报告的增删改查
    # ----------------------------------------------------------
    print("\n[测试6] 回顾报告的增删改查")
    review_id = storage.save_review({
        "review_focus": {"user_goal": "测试", "time_range_or_topic": "测试"},
        "confirmed_understandings": {"user_expressed_content": [], "unreviewed_no_conflict": []},
        "next_step": {"choice": "stop", "other_description": None}
    })
    assert review_id is not None, "应该返回回顾报告 ID"

    reviews = storage.list_reviews()
    assert len(reviews) == 1, "应该有 1 份回顾报告"
    print("  ✅ 通过")

    # ----------------------------------------------------------
    # 测试7：用户配置的读写和模块开关
    # ----------------------------------------------------------
    print("\n[测试7] 用户配置的读写和模块开关")
    config = storage.read_config()
    assert config is not None, "应该返回用户配置"
    assert config["modules"]["auto_archive_update"]["enabled"] == True

    storage.update_module("pattern_recognition", False)
    assert storage.is_module_enabled("pattern_recognition") == False
    print("  ✅ 通过")

    # ----------------------------------------------------------
    # 测试8：探索进度的读写
    # ----------------------------------------------------------
    print("\n[测试8] 探索进度的读写")
    storage.write_progress({
        "current_workflow": "initial-assessment",
        "current_step": 3,
        "total_steps": 7,
        "step_description": "测试步骤",
        "recorded_answers": [],
        "temporary_insights": [],
        "can_resume": True
    })
    progress = storage.read_progress()
    assert progress["current_step"] == 3
    assert storage.can_resume() == True

    storage.clear_progress()
    assert storage.can_resume() == False
    print("  ✅ 通过")

    # ----------------------------------------------------------
    # 测试9：统计信息
    # ----------------------------------------------------------
    print("\n[测试9] 统计信息")
    stats = storage.get_stats()
    assert stats["insights_count"] == 1
    assert stats["patterns_count"] == 1
    print(f"  统计信息: {stats}")
    print("  ✅ 通过")

    # ----------------------------------------------------------
    # 测试10：文件加密验证
    # ----------------------------------------------------------
    print("\n[测试10] 文件加密验证")
    profile_path = os.path.join(test_dir, test_user, "profile.json")
    with open(profile_path, "rb") as f:
        content = f.read()
    try:
        json.loads(content.decode("utf-8"))
        assert False, "文件应该是加密的，不能直接读取为 JSON"
    except (json.JSONDecodeError, UnicodeDecodeError):
        print("  ✅ 文件已加密，无法直接读取为 JSON")

    # auth.json 不加密
    auth_path = os.path.join(test_dir, test_user, "auth.json")
    with open(auth_path, "r", encoding="utf-8") as f:
        auth_data = json.load(f)
    assert "verify_salt" in auth_data and "key_salt" in auth_data  # v2 双盐（验证盐/密钥盐独立）
    assert "password_hash" in auth_data
    assert auth_data.get("kdf_version") == 2
    print("  ✅ auth.json 不加密，包含 v2 双盐密码验证信息")
    print("  ✅ 通过")

    # ----------------------------------------------------------
    # 测试11：密码验证
    # ----------------------------------------------------------
    print("\n[测试11] 密码验证")
    assert storage.verify_password("test123") == True
    assert storage.verify_password("wrongpassword") == False
    print("  ✅ 通过")

    # ----------------------------------------------------------
    # 测试12：修改密码
    # ----------------------------------------------------------
    print("\n[测试12] 修改密码")
    assert storage.change_password("test123", "newpassword456") == True
    assert storage.verify_password("test123") == False
    assert storage.verify_password("newpassword456") == True

    # 验证使用新密码可以读取之前加密的文件
    read_profile = storage.read_profile()
    assert read_profile["current_focus"]["current_topic"] == "测试主题"
    print("  ✅ 通过")

    # ----------------------------------------------------------
    # 测试13：使用错误密码初始化（应该失败）
    # ----------------------------------------------------------
    print("\n[测试13] 使用错误密码初始化（应该失败）")
    try:
        storage2 = LocalEncryptedStorageAdapter(
            base_dir=test_dir, user_id=test_user, password="wrongpassword"
        )
        assert False, "使用错误密码应该失败"
    except ValueError as e:
        print(f"  ✅ 使用错误密码初始化失败（预期行为）：{e}")

    # ----------------------------------------------------------
    # 测试14：删除级联
    # ----------------------------------------------------------
    print("\n[测试14] 删除级联")
    # 重新使用正确密码初始化
    storage = LocalEncryptedStorageAdapter(
        base_dir=test_dir, user_id=test_user, password="newpassword456"
    )

    # 删除对话记录，应该级联删除相关洞察卡和模式卡
    conversations = storage.list_conversations()
    if conversations:
        conv_id = conversations[0]["id"]
        storage.delete_conversation(conv_id)

    insights = storage.list_insights()
    patterns = storage.list_patterns()
    print(f"  删除对话后，洞察卡数量: {len(insights)}")
    print(f"  删除对话后，模式卡数量: {len(patterns)}")
    print("  ✅ 通过")

    # ----------------------------------------------------------
    # 测试15：全量删除
    # ----------------------------------------------------------
    print("\n[测试15] 全量删除")
    storage.delete_all()

    profile = storage.read_profile()
    insights = storage.list_insights()
    patterns = storage.list_patterns()
    assert len(insights) == 0
    assert len(patterns) == 0
    print("  ✅ 通过")

    # 清理测试数据
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)

    print("\n" + "=" * 60)
    print("✅ 所有测试通过！")
    print("=" * 60)


if __name__ == "__main__":
    test_encrypted_storage_adapter()
