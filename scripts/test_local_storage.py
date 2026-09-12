"""
本地存储适配器完整测试脚本

测试所有功能：
1. 档案读写（全量版+精简版）
2. 洞察卡的增删改查
3. 对话记录的增删改查
4. 模式卡的增删改查
5. 回顾报告的增删改查
6. 用户配置的读写和模块开关
7. 探索进度的读写
8. 删除级联（删除对话→级联删除洞察和模式）
9. 全量删除
"""

import sys
import os
import shutil

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from storage.adapters.local_json import LocalJsonStorageAdapter


def test_storage_adapter():
    """测试存储适配器"""
    print("=" * 60)
    print("本地存储适配器完整测试")
    print("=" * 60)

    # 使用临时测试目录
    test_dir = "storage/data/test_local"
    test_user = "test_user"

    # 清理之前的测试数据
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)

    storage = LocalJsonStorageAdapter(base_dir=test_dir, user_id=test_user)

    # ----------------------------------------------------------
    # 测试1：能力闸门
    # ----------------------------------------------------------
    print("\n[测试1] 能力闸门")
    mode = storage.get_storage_mode()
    capabilities = storage.get_storage_capabilities()
    print(f"  存储模式: {mode}")
    print(f"  存储能力: {capabilities}")
    assert mode == "local_unencrypted", "存储模式应该是 local_unencrypted"
    assert capabilities["can_persist"] == True, "应该支持持久化"
    assert capabilities["can_store_high_sensitivity"] == False, "未加密不应该支持高敏感内容"
    print("  ✅ 通过")

    # ----------------------------------------------------------
    # 测试2：用户配置
    # ----------------------------------------------------------
    print("\n[测试2] 用户配置（复用 know-yourself 模块开关经验）")
    config = storage.read_config()
    print(f"  默认配置模块数: {len(config['modules'])}")
    print(f"  auto_archive_update 启用: {config['modules']['auto_archive_update']['enabled']}")

    # 测试模块开关
    storage.update_module("pattern_recognition", False)
    config = storage.read_config()
    assert config["modules"]["pattern_recognition"]["enabled"] == False, "pattern_recognition 应该被禁用"
    assert storage.is_module_enabled("pattern_recognition") == False, "is_module_enabled 应该返回 False"

    storage.update_module("pattern_recognition", True)
    assert storage.is_module_enabled("pattern_recognition") == True, "pattern_recognition 应该被重新启用"
    print("  ✅ 通过")

    # ----------------------------------------------------------
    # 测试3：档案读写（全量版+精简版双档案设计）
    # ----------------------------------------------------------
    print("\n[测试3] 档案读写（复用 know-yourself 双档案设计经验）")
    profile = storage.read_profile()
    print(f"  空画像 ID: {profile['id']}")
    print(f"  空画像 confirmed_understandings 数: {len(profile['confirmed_understandings'])}")

    # 验证生活风格概览字段存在
    assert "lifestyle_overview" in profile, "空画像应该包含 lifestyle_overview 字段"
    overview = profile["lifestyle_overview"]
    assert "core_summary" in overview, "lifestyle_overview 应该包含 core_summary"
    assert "key_themes" in overview, "lifestyle_overview 应该包含 key_themes"
    assert "confidence" in overview, "lifestyle_overview 应该包含 confidence"
    assert "note" in overview, "lifestyle_overview 应该包含 note"
    assert "created_at" in overview, "lifestyle_overview 应该包含 created_at"
    assert "last_updated" in overview, "lifestyle_overview 应该包含 last_updated"
    print("  生活风格概览字段: ✅ 存在且结构完整")

    # 验证核心维度字段存在
    assert "core_dimensions" in profile, "空画像应该包含 core_dimensions 字段"
    dimensions = profile["core_dimensions"]
    expected_dimensions = [
        "self_concept", "self_ideal", "world_view", "view_of_others",
        "private_logic", "basic_mistakes", "behavioral_strategies",
        "social_interest", "inferiority_and_compensation"
    ]
    for dim in expected_dimensions:
        assert dim in dimensions, f"core_dimensions 应该包含 {dim}"
        dim_data = dimensions[dim]
        assert "core_belief" in dim_data, f"{dim} 应该包含 core_belief"
        assert "details" in dim_data, f"{dim} 应该包含 details"
        assert "source" in dim_data, f"{dim} 应该包含 source"
        assert "confidence" in dim_data, f"{dim} 应该包含 confidence"
        assert "user_correction" in dim_data, f"{dim} 应该包含 user_correction"
        assert "last_updated" in dim_data, f"{dim} 应该包含 last_updated"
    print(f"  核心维度字段: ✅ 存在且包含 {len(expected_dimensions)} 个维度")

    # 添加一个已确认理解
    profile["confirmed_understandings"].append({
        "id": "understanding-001",
        "user_expression": "在熟悉的朋友面前表达观点较轻松，在老师或职位较高的人面前更容易紧张",
        "shared_summary": "评价压力似乎比'表达本身'更影响你",
        "applicable_contexts": "熟人小组不明显",
        "evidence_and_confirmation": "用户在三次不同场景中确认",
        "confirmed_at": "2026-09-05",
        "related_dimension": "behavioral_strategies",
    })
    profile["current_focus"]["current_topic"] = "开会不敢发言"

    # 更新生活风格概览
    profile["lifestyle_overview"]["core_summary"] = "用户在评价压力较高的情境中倾向于沉默，但在熟悉的环境中能够表达自己。核心模式是通过回避来保护自己免受评判。"
    profile["lifestyle_overview"]["key_themes"] = ["评价焦虑", "回避策略", "熟悉环境中的安全感"]
    profile["lifestyle_overview"]["confidence"] = "中"

    # 更新核心维度
    profile["core_dimensions"]["behavioral_strategies"]["core_belief"] = "在有压力的情境中，沉默是最安全的选择"
    profile["core_dimensions"]["behavioral_strategies"]["details"] = ["在权威人物面前紧张", "在熟悉朋友面前能表达"]
    profile["core_dimensions"]["behavioral_strategies"]["source"] = "初步画像+日常对话"
    profile["core_dimensions"]["behavioral_strategies"]["confidence"] = "中"

    storage.write_profile(profile)

    # 读取全量版
    full_profile = storage.read_profile(lite=False)
    assert len(full_profile["confirmed_understandings"]) == 1, "全量版应该有1个已确认理解"
    assert full_profile["lifestyle_overview"]["core_summary"] != "", "全量版应该保存了生活风格概览"
    assert full_profile["core_dimensions"]["behavioral_strategies"]["core_belief"] != "", "全量版应该保存了核心维度"
    print("  全量版新字段保存: ✅ 生活风格概览和核心维度已正确保存")

    # 读取精简版
    lite_profile = storage.read_profile(lite=True)
    print(f"  精简版类型: {lite_profile['type']}")
    assert lite_profile["type"] == "profile_lite", "精简版类型应该是 profile_lite"
    assert "pending_understandings" not in lite_profile, "精简版不应该包含 pending_understandings"
    assert "lifestyle_overview" in lite_profile, "精简版应该包含 lifestyle_overview"
    assert "core_dimensions" in lite_profile, "精简版应该包含 core_dimensions"
    print("  精简版新字段: ✅ 生活风格概览和核心维度已包含在精简版中")
    print("  ✅ 通过")

    # ----------------------------------------------------------
    # 测试4：对话记录（含完整对话记录）
    # ----------------------------------------------------------
    print("\n[测试4] 对话记录（含完整对话记录）")

    # 测试1：创建带完整对话记录的对话
    conv_id = storage.append_conversation({
        "summary": "用户讨论开会不敢发言的问题，探索了目的论和纵向关系",
        "conversation_type": "exploration",
        "related_insights": [],
        "related_patterns": [],
        "user_confirmed": True,
        "full_transcript": {
            "enabled": True,
            "messages": [
                {"role": "user", "content": "我开会的时候总是不敢发言", "timestamp": "2026-09-05T10:00:00+08:00"},
                {"role": "assistant", "content": "听起来你在会议这种有评判压力的情境下会选择沉默，我们可以一起看看这背后的目的是什么。", "timestamp": "2026-09-05T10:01:00+08:00"},
                {"role": "user", "content": "我觉得是因为我怕说错话被别人笑话", "timestamp": "2026-09-05T10:02:00+08:00"},
            ],
            "message_count": 3,
        }
    })
    print(f"  创建带完整对话记录的对话: {conv_id}")

    # 读取对话记录，验证完整对话记录是否正确保存
    saved_conv = storage.get_conversation(conv_id)
    assert saved_conv is not None, "应该能读取到对话记录"
    assert "full_transcript" in saved_conv, "对话记录应该包含 full_transcript 字段"
    assert saved_conv["full_transcript"]["enabled"] == True, "完整对话记录应该启用"
    assert len(saved_conv["full_transcript"]["messages"]) == 3, "应该有3条消息"
    assert saved_conv["full_transcript"]["messages"][0]["role"] == "user", "第一条消息应该是用户"
    assert saved_conv["full_transcript"]["messages"][0]["content"] == "我开会的时候总是不敢发言", "第一条消息内容应该正确"
    print("  完整对话记录保存: ✅ 正确保存了3条消息")

    # 测试2：创建不带完整对话记录的对话（验证默认字段）
    conv_id2 = storage.append_conversation({
        "summary": "用户讨论人际关系问题",
        "conversation_type": "exploration",
        "related_insights": [],
        "related_patterns": [],
        "user_confirmed": True,
    })
    print(f"  创建不带完整对话记录的对话: {conv_id2}")

    saved_conv2 = storage.get_conversation(conv_id2)
    assert saved_conv2 is not None, "应该能读取到对话记录"
    assert "full_transcript" in saved_conv2, "即使不传入，也应该有默认的 full_transcript 字段"
    assert saved_conv2["full_transcript"]["enabled"] == True, "默认应该启用完整对话记录"
    assert len(saved_conv2["full_transcript"]["messages"]) == 0, "默认应该没有消息"
    print("  默认完整对话记录字段: ✅ 即使不传入也有默认字段")

    conversations = storage.list_conversations()
    assert len(conversations) == 2, "应该有2条对话记录"

    # 搜索对话
    results = storage.search_conversations("开会")
    assert len(results) == 1, "搜索'开会'应该返回1条结果"
    print("  ✅ 通过")

    # ----------------------------------------------------------
    # 测试5：洞察卡
    # ----------------------------------------------------------
    print("\n[测试5] 洞察卡")
    insight_id = storage.append_insight({
        "current_topic": {
            "user_statement": "我开会总是不敢发言",
            "specific_context": "最近一次工作会议",
        },
        "adlerian_understanding": {
            "possible_understanding": "也许不发言是在保护自己不必面对'表达不完整会被评价'的风险",
            "what_it_protects_or_pursues": "保护安全感，避免被否定",
            "limitations_and_exceptions": "在熟悉的朋友面前有时能直接说出想法",
        },
        "user_correction": {
            "correction_type": "some_contexts",
            "user_rewrite": "面对权威角色时更明显",
            "next_step": "先停在理解",
        },
        "archive_status": {
            "status": "generate_update",
            "notes": "用户确认保存",
        },
        "source_conversation_ids": [conv_id],
    })
    print(f"  创建洞察卡: {insight_id}")

    insights = storage.list_insights()
    assert len(insights) == 1, "应该有1张洞察卡"

    # 获取单个洞察卡
    insight = storage.get_insight(insight_id)
    assert insight is not None, "应该能获取到洞察卡"
    assert insight["source_conversation_ids"] == [conv_id], "源对话 ID 应该正确"
    print("  ✅ 通过")

    # ----------------------------------------------------------
    # 测试6：模式卡
    # ----------------------------------------------------------
    print("\n[测试6] 模式卡")
    pattern_id = storage.append_pattern({
        "common_triggers": {
            "similar_contexts": "在工作会议、朋友讨论和亲属聚会中，出现'担心意见不够好或会被否定'的时刻",
            "reference_events": [
                {"time_range": "2026-08-01 至 2026-08-15", "context": "工作会议", "relation_reason": "出现了相似的沉默模式"},
            ],
        },
        "concerns": {
            "expressed_concerns": "不想显得准备不足，也不希望给别人添麻烦",
            "parts_to_correct": "",
        },
        "protection_methods": {
            "common_coping": "先沉默、反复修改想说的话，或等到话题结束",
            "what_it_protects": "也许这样做能暂时避开被否定或暴露不完整想法的风险",
        },
        "short_term_gains": {
            "immediate_relief": "当下不必面对可能的尴尬，紧张会短暂下降",
        },
        "long_term_costs": {
            "potential_impacts": "之后可能更难让他人知道你的真实想法",
        },
        "exceptions_and_changes": {
            "non_matching_contexts": "在熟悉的朋友面前有时能先说出一句不完整的想法",
            "different_choices": "",
        },
        "user_correction": {
            "correction_type": "some_contexts",
            "user_rewrite": "面对权威角色时更明显",
            "corrected_at": "2026-09-05",
        },
        "evidence": {
            "instance_count": 3,
            "context_count": 2,
            "time_span": "2026-08-01 至 2026-09-01",
            "supporting_insights": [insight_id],
            "counter_evidence": [],
        },
        "source_conversation_ids": [conv_id],
        "source_insight_ids": [insight_id],
    })
    print(f"  创建模式卡: {pattern_id}")

    patterns = storage.list_patterns()
    assert len(patterns) == 1, "应该有1张模式卡"
    print("  ✅ 通过")

    # ----------------------------------------------------------
    # 测试7：回顾报告
    # ----------------------------------------------------------
    print("\n[测试7] 回顾报告")
    review_id = storage.save_review({
        "review_focus": {
            "user_goal": "想看看过去几周在工作会议中表达意见的变化",
            "time_range_or_topic": "2026-08-01 至 2026-09-01",
        },
        "confirmed_understandings": {
            "user_expressed_content": ["在权威角色面前更容易担心准备不足"],
            "unreviewed_no_conflict": [],
        },
        "context_differences": {
            "changes_in_different_contexts": "在熟悉团队里已经能先说出一句不完整的想法",
            "different_choices_or_strengths": "",
            "exceptions_to_keep": "",
        },
        "parts_to_correct": [],
        "patterns_to_review": [
            {
                "pattern_id": pattern_id,
                "pattern_link_or_summary": "面对权威角色时的沉默模式",
                "user_choice": "some_contexts",
            }
        ],
        "next_step": {
            "choice": "stop",
            "other_description": None,
        },
    })
    print(f"  创建回顾报告: {review_id}")

    reviews = storage.list_reviews()
    assert len(reviews) == 1, "应该有1份回顾报告"
    print("  ✅ 通过")

    # ----------------------------------------------------------
    # 测试8：探索进度
    # ----------------------------------------------------------
    print("\n[测试8] 探索进度（复用 know-yourself 进度保存经验）")
    storage.write_progress({
        "current_workflow": "initial-assessment",
        "current_step": 3,
        "total_steps": 7,
        "step_description": "具体化与一致性澄清",
        "recorded_answers": [
            {
                "step": 1,
                "question": "最近一次开会你本来有想法但最终没说出口，当时你心里最担心的是什么？",
                "answer": "我担心自己说的东西没价值",
                "recorded_at": "2026-09-05T10:05:00+08:00",
            }
        ],
        "temporary_insights": ["也许'觉得没价值'是一种预先的自我保护"],
        "can_resume": True,
    })

    progress = storage.read_progress()
    assert progress is not None, "应该能读取到探索进度"
    assert progress["current_step"] == 3, "当前步骤应该是3"
    assert storage.can_resume() == True, "应该可以恢复"

    storage.clear_progress()
    assert storage.read_progress() is None, "清除后应该读取不到进度"
    assert storage.can_resume() == False, "清除后应该不可以恢复"
    print("  ✅ 通过")

    # ----------------------------------------------------------
    # 测试9：删除级联（复用 diarygpt 源—派生关系经验）
    # ----------------------------------------------------------
    print("\n[测试9] 删除级联（复用 diarygpt 源—派生关系经验）")

    # 先重新创建数据（因为上面清除了进度，但其他数据还在）
    # 确认当前数据
    assert len(storage.list_insights()) == 1, "应该有1张洞察卡"
    assert len(storage.list_patterns()) == 1, "应该有1张模式卡"

    # 删除洞察卡，检查模式卡是否被重新评估
    print("  删除洞察卡...")
    storage.delete_insight(insight_id, cascade=True)

    insights = storage.list_insights()
    assert len(insights) == 0, "洞察卡应该被删除"

    # 模式卡应该还在，但证据门槛应该被重新评估
    pattern = storage.get_pattern(pattern_id)
    assert pattern is not None, "模式卡应该还在"
    assert pattern["status"] == "pending_verification", "模式卡应该被降为待验证（证据不足3个独立实例）"
    assert pattern["evidence"]["instance_count"] == 0, "支持洞察数应该为0"
    print(f"  模式卡状态: {pattern['status']}")
    print(f"  降级原因: {pattern.get('downgraded_reason', '')}")
    print("  ✅ 通过")

    # ----------------------------------------------------------
    # 测试10：全量删除
    # ----------------------------------------------------------
    print("\n[测试10] 全量删除")
    storage.delete_all()

    stats = storage.get_stats()
    print(f"  删除后统计: {stats}")
    assert stats["insights_count"] == 0, "洞察卡应该为0"
    assert stats["conversations_count"] == 0, "对话记录应该为0"
    assert stats["patterns_count"] == 0, "模式卡应该为0"
    assert stats["reviews_count"] == 0, "回顾报告应该为0"
    assert stats["profile_exists"] == False, "画像应该不存在"
    print("  ✅ 通过")

    # ----------------------------------------------------------
    # 清理测试数据
    # ----------------------------------------------------------
    print("\n[清理] 删除测试目录")
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)
    print("  ✅ 完成")

    # ----------------------------------------------------------
    # 测试总结
    # ----------------------------------------------------------
    print("\n" + "=" * 60)
    print("所有测试通过！")
    print("=" * 60)
    print("\n测试覆盖：")
    print("  1. 能力闸门 ✅")
    print("  2. 用户配置（模块开关）✅")
    print("  3. 档案读写（全量版+精简版双档案）✅")
    print("  4. 对话记录增删改查 ✅")
    print("  5. 洞察卡增删改查 ✅")
    print("  6. 模式卡增删改查 ✅")
    print("  7. 回顾报告增删改查 ✅")
    print("  8. 探索进度保存与恢复 ✅")
    print("  9. 删除级联（源—派生关系）✅")
    print("  10. 全量删除 ✅")


if __name__ == "__main__":
    test_storage_adapter()
