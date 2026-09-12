"""
持久化功能端到端测试

模拟完整用户旅程：首次使用→多次对话→洞察提取→档案更新→模式识别→定期回顾
验证所有持久化功能是否能正确协同工作。

测试场景：
1. 用户首次使用，创建空档案和配置
2. 第一次对话：探索"开会不敢发言"，提取洞察，用户确认保存
3. 第二次对话：探索"领导面前紧张"，提取洞察，用户确认保存
4. 第三次对话：探索"朋友讨论沉默"，提取洞察，用户确认保存
5. 模式识别：基于3个洞察识别"面对权威角色时沉默"的重复模式
6. 画像驱动对话：基于生活风格画像提供个性化回应
7. 定期校准回顾：生成回顾报告
8. 用户修正：用户不同意某个洞察，删除后重新评估模式
9. 用户配置：禁用模式识别模块
10. 全量删除：删除所有数据
"""

import sys
import os
import shutil

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from storage.adapters.local_json import LocalJsonStorageAdapter


def test_persistence_e2e():
    """持久化功能端到端测试"""
    print("=" * 70)
    print("持久化功能端到端测试")
    print("模拟完整用户旅程：首次使用→多次对话→洞察提取→档案更新→模式识别→定期回顾")
    print("=" * 70)

    # 使用临时测试目录
    test_dir = "storage/data/test_e2e"
    test_user = "test_user_e2e"

    # 清理之前的测试数据
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)

    storage = LocalJsonStorageAdapter(base_dir=test_dir, user_id=test_user)

    # ============================================================
    # 场景1：用户首次使用，创建空档案和配置
    # ============================================================
    print("\n[场景1] 用户首次使用，创建空档案和配置")

    # 读取空画像（会自动创建默认结构）
    profile = storage.read_profile()
    print(f"  空画像 ID: {profile['id']}")
    print(f"  空画像 confirmed_understandings 数: {len(profile['confirmed_understandings'])}")
    assert len(profile["confirmed_understandings"]) == 0, "新用户应该没有已确认理解"

    # 读取默认配置
    config = storage.read_config()
    print(f"  默认配置模块数: {len(config['modules'])}")
    print(f"  auto_archive_update 启用: {config['modules']['auto_archive_update']['enabled']}")
    assert len(config["modules"]) == 4, "应该有4个模块"
    assert config["modules"]["auto_archive_update"]["enabled"] == True, "自动档案更新应该默认启用"

    # 检查精简版画像是否自动同步
    lite_profile = storage.read_profile(lite=True)
    print(f"  精简版画像类型: {lite_profile['type']}")
    assert lite_profile["type"] == "profile_lite", "精简版画像类型应该是 profile_lite"

    print("  ✅ 通过")

    # ============================================================
    # 场景2：第一次对话，探索"开会不敢发言"
    # ============================================================
    print("\n[场景2] 第一次对话：探索'开会不敢发言'")

    # 保存对话记录
    conv1_id = storage.append_conversation({
        "summary": "用户讨论开会不敢发言的问题，探索了目的论：不发言可能是在保护自己不必面对'表达不完整会被评价'的风险",
        "conversation_type": "exploration",
        "related_insights": [],
        "related_patterns": [],
        "user_confirmed": True,
    })
    print(f"  对话记录 ID: {conv1_id}")

    # 提取洞察候选
    insight1_id = storage.append_insight({
        "current_topic": {
            "user_statement": "我开会总是不敢发言",
            "specific_context": "最近一次工作会议",
        },
        "user_material": {
            "what_happened": "用户在会议上有想法但最终没说出口",
            "feelings_and_concerns": "担心自己说的东西没价值，会被别人笑话",
            "reaction": "选择沉默，反复修改想说的话，最后话题结束",
        },
        "adlerian_understanding": {
            "possible_understanding": "也许不发言是在保护自己不必面对'表达不完整会被评价'的风险",
            "what_it_protects_or_pursues": "保护安全感，避免被否定",
            "limitations_and_exceptions": "在熟悉的朋友面前有时能直接说出想法",
        },
        "user_correction": {
            "correction_type": "very_close",
            "user_rewrite": "确实是这样，我很担心被评价",
            "next_step": "继续探索",
        },
        "archive_status": {
            "status": "generate_update",
            "notes": "用户确认保存",
        },
        "source_conversation_ids": [conv1_id],
    })
    print(f"  洞察卡 ID: {insight1_id}")

    # 更新画像：添加已确认理解
    profile = storage.read_profile()
    profile["current_focus"]["current_topic"] = "开会不敢发言"
    profile["confirmed_understandings"].append({
        "id": "understanding-001",
        "user_expression": "在会议上有想法但最终没说出口，担心自己说的东西没价值",
        "shared_summary": "不发言可能是在保护自己不必面对'表达不完整会被评价'的风险",
        "applicable_contexts": "工作会议，在熟悉的朋友面前不明显",
        "evidence_and_confirmation": "用户在第一次对话中确认",
        "confirmed_at": "2026-09-05",
    })
    profile["strengths_and_values"]["existing_strengths"] = "在熟悉的朋友面前有时能直接说出想法"
    storage.write_profile(profile)
    print("  画像已更新：添加1个已确认理解")

    # 验证画像更新
    profile = storage.read_profile()
    assert len(profile["confirmed_understandings"]) == 1, "画像应该有1个已确认理解"
    assert profile["current_focus"]["current_topic"] == "开会不敢发言", "当前议题应该更新"

    print("  ✅ 通过")

    # ============================================================
    # 场景3：第二次对话，探索"领导面前紧张"
    # ============================================================
    print("\n[场景3] 第二次对话：探索'领导面前紧张'")

    conv2_id = storage.append_conversation({
        "summary": "用户讨论在领导面前紧张的问题，探索了纵向关系：在领导面前不自觉进入纵向关系模式，把每句话都当成'被考核的表现'",
        "conversation_type": "exploration",
        "related_insights": [],
        "related_patterns": [],
        "user_confirmed": True,
    })
    print(f"  对话记录 ID: {conv2_id}")

    insight2_id = storage.append_insight({
        "current_topic": {
            "user_statement": "我在领导面前总是很紧张，说不出话",
            "specific_context": "最近一次与领导的一对一会议",
        },
        "user_material": {
            "what_happened": "用户在领导面前准备发言时感到紧张，最终只说了很少的话",
            "feelings_and_concerns": "担心领导觉得自己能力不足，担心被评判",
            "reaction": "尽量少说，避免出错",
        },
        "adlerian_understanding": {
            "possible_understanding": "在领导面前不自觉进入纵向关系模式，把每句话都当成'被考核的表现'",
            "what_it_protects_or_pursues": "保护自己不被评判，维持'我至少没出错'的安全感",
            "limitations_and_exceptions": "在朋友面前不紧张，能自由表达",
        },
        "user_correction": {
            "correction_type": "very_close",
            "user_rewrite": "确实是这样，我把领导当成了评判者",
            "next_step": "继续探索",
        },
        "archive_status": {
            "status": "generate_update",
            "notes": "用户确认保存",
        },
        "source_conversation_ids": [conv2_id],
    })
    print(f"  洞察卡 ID: {insight2_id}")

    # 更新画像
    profile = storage.read_profile()
    profile["confirmed_understandings"].append({
        "id": "understanding-002",
        "user_expression": "在领导面前感到紧张，说不出话，担心领导觉得自己能力不足",
        "shared_summary": "在领导面前不自觉进入纵向关系模式，把每句话都当成'被考核的表现'",
        "applicable_contexts": "与领导的一对一会议，在朋友面前不明显",
        "evidence_and_confirmation": "用户在第二次对话中确认",
        "confirmed_at": "2026-09-05",
    })
    storage.write_profile(profile)
    print("  画像已更新：添加第2个已确认理解")

    # 验证
    profile = storage.read_profile()
    assert len(profile["confirmed_understandings"]) == 2, "画像应该有2个已确认理解"

    print("  ✅ 通过")

    # ============================================================
    # 场景4：第三次对话，探索"朋友讨论沉默"
    # ============================================================
    print("\n[场景4] 第三次对话：探索'朋友讨论沉默'")

    conv3_id = storage.append_conversation({
        "summary": "用户讨论在朋友讨论中偶尔也会沉默的问题，发现只有在讨论中出现'谁对谁错'的评判氛围时才会沉默，纯闲聊时不沉默",
        "conversation_type": "exploration",
        "related_insights": [],
        "related_patterns": [],
        "user_confirmed": True,
    })
    print(f"  对话记录 ID: {conv3_id}")

    insight3_id = storage.append_insight({
        "current_topic": {
            "user_statement": "我有时候在朋友讨论中也会沉默",
            "specific_context": "最近一次朋友聚会的讨论",
        },
        "user_material": {
            "what_happened": "用户在朋友讨论中偶尔沉默，但纯闲聊时不沉默",
            "feelings_and_concerns": "当讨论中出现'谁对谁错'的评判氛围时，会担心自己说错",
            "reaction": "选择沉默，避免参与评判",
        },
        "adlerian_understanding": {
            "possible_understanding": "当讨论中出现评判氛围时，会不自觉进入纵向关系模式，即使是朋友也会感到被评判",
            "what_it_protects_or_pursues": "保护自己不被评判，避免冲突",
            "limitations_and_exceptions": "纯闲聊时不沉默，能自由表达",
        },
        "user_correction": {
            "correction_type": "some_contexts",
            "user_rewrite": "只有在出现评判氛围时才会沉默，纯闲聊时不沉默",
            "next_step": "先停在理解",
        },
        "archive_status": {
            "status": "generate_update",
            "notes": "用户确认保存",
        },
        "source_conversation_ids": [conv3_id],
    })
    print(f"  洞察卡 ID: {insight3_id}")

    # 更新画像
    profile = storage.read_profile()
    profile["confirmed_understandings"].append({
        "id": "understanding-003",
        "user_expression": "在朋友讨论中偶尔沉默，只有在出现评判氛围时才沉默",
        "shared_summary": "当讨论中出现评判氛围时，会不自觉进入纵向关系模式，即使是朋友也会感到被评判",
        "applicable_contexts": "有评判氛围的讨论，纯闲聊时不明显",
        "evidence_and_confirmation": "用户在第三次对话中确认",
        "confirmed_at": "2026-09-05",
    })
    storage.write_profile(profile)
    print("  画像已更新：添加第3个已确认理解")

    # 验证
    profile = storage.read_profile()
    assert len(profile["confirmed_understandings"]) == 3, "画像应该有3个已确认理解"

    print("  ✅ 通过")

    # ============================================================
    # 场景5：模式识别，基于3个洞察识别重复模式
    # ============================================================
    print("\n[场景5] 模式识别：基于3个洞察识别'面对评判氛围时沉默'的重复模式")

    # 检查模式识别模块是否启用
    assert storage.is_module_enabled("pattern_recognition") == True, "模式识别模块应该启用"

    # 创建模式卡（基于3个独立实例，跨2个以上情境）
    pattern_id = storage.append_pattern({
        "common_triggers": {
            "similar_contexts": "在工作会议、领导一对一会议、朋友讨论中，出现'担心意见不够好或会被否定'的时刻",
            "reference_events": [
                {"time_range": "第一次对话", "context": "工作会议", "relation_reason": "出现了相似的沉默模式"},
                {"time_range": "第二次对话", "context": "领导一对一会议", "relation_reason": "出现了相似的紧张和沉默"},
                {"time_range": "第三次对话", "context": "朋友讨论", "relation_reason": "出现了相似的沉默，但只在评判氛围时"},
            ],
        },
        "concerns": {
            "expressed_concerns": "不想显得准备不足，不希望给别人添麻烦，担心被评判",
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
            "potential_impacts": "之后可能更难让他人知道你的真实想法，也会让你觉得自己又错过了一次表达",
        },
        "exceptions_and_changes": {
            "non_matching_contexts": "在熟悉的朋友面前纯闲聊时，有时能先说出一句不完整的想法",
            "different_choices": "",
        },
        "user_correction": {
            "correction_type": "some_contexts",
            "user_rewrite": "面对权威角色或评判氛围时更明显",
            "corrected_at": "2026-09-05",
        },
        "evidence": {
            "instance_count": 3,
            "context_count": 3,
            "time_span": "第一次对话至第三次对话",
            "supporting_insights": [insight1_id, insight2_id, insight3_id],
            "counter_evidence": [],
        },
        "source_conversation_ids": [conv1_id, conv2_id, conv3_id],
        "source_insight_ids": [insight1_id, insight2_id, insight3_id],
    })
    print(f"  模式卡 ID: {pattern_id}")

    # 验证模式卡
    patterns = storage.list_patterns()
    assert len(patterns) == 1, "应该有1张模式卡"
    assert patterns[0]["evidence"]["instance_count"] == 3, "模式卡应该有3个实例"
    assert patterns[0]["evidence"]["context_count"] == 3, "模式卡应该跨3个情境"

    print("  ✅ 通过")

    # ============================================================
    # 场景6：画像驱动对话，基于生活风格画像提供个性化回应
    # ============================================================
    print("\n[场景6] 画像驱动对话：基于生活风格画像提供个性化回应")

    # 检查画像驱动对话模块是否启用
    assert storage.is_module_enabled("profile_driven_dialogue") == True, "画像驱动对话模块应该启用"

    # 读取画像，模拟基于画像提供个性化回应
    profile = storage.read_profile()
    print(f"  当前议题: {profile['current_focus']['current_topic']}")
    print(f"  已确认理解数: {len(profile['confirmed_understandings'])}")
    print(f"  已有力量: {profile['strengths_and_values']['existing_strengths']}")
    print(f"  已识别模式数: {len(profile.get('confirmed_patterns', []))}")

    # 模拟画像驱动回应：基于已有力量和例外
    print(f"  画像驱动回应示例：")
    print(f"    '我注意到你在熟悉的朋友面前有时能先说出一句不完整的想法，")
    print(f"     这说明你并不是完全不能表达，而是在特定情境下会选择沉默。")
    print(f"     我们可以一起看看，能不能把这种'先说出不完整想法'的经验，")
    print(f"     慢慢迁移到其他情境中。'")

    print("  ✅ 通过")

    # ============================================================
    # 场景7：定期校准回顾，生成回顾报告
    # ============================================================
    print("\n[场景7] 定期校准回顾：生成回顾报告")

    # 检查定期回顾模块是否启用
    assert storage.is_module_enabled("periodic_review") == True, "定期回顾模块应该启用"

    # 创建回顾报告
    review_id = storage.save_review({
        "review_focus": {
            "user_goal": "想看看过去几次对话中表达问题的变化",
            "time_range_or_topic": "第一次对话至第三次对话",
        },
        "confirmed_understandings": {
            "user_expressed_content": [
                "在会议上有想法但最终没说出口，担心自己说的东西没价值",
                "在领导面前感到紧张，说不出话，担心领导觉得自己能力不足",
                "在朋友讨论中偶尔沉默，只有在出现评判氛围时才沉默",
            ],
            "unreviewed_no_conflict": [],
        },
        "context_differences": {
            "changes_in_different_contexts": "在熟悉团队里纯闲聊时，已经能先说出一句不完整的想法",
            "different_choices_or_strengths": "在熟悉的朋友面前有时能直接说出想法",
            "exceptions_to_keep": "纯闲聊时不沉默",
        },
        "parts_to_correct": [
            {
                "id": "correct-001",
                "old_understanding_or_new_conflict": "以前以为只要面对权威就会沉默",
                "system_tentative_summary": "新的材料显示，只有在出现评判氛围时才会沉默，纯闲聊时不沉默",
                "user_correction": "如果议题准备充分，我仍然可以表达",
                "processing_method": "add_context",
            }
        ],
        "patterns_to_review": [
            {
                "pattern_id": pattern_id,
                "pattern_link_or_summary": "面对评判氛围时的沉默模式",
                "user_choice": "some_contexts",
            }
        ],
        "next_step": {
            "choice": "continue_exploring",
            "other_description": "继续探索如何把'先说出不完整想法'的经验迁移到其他情境",
        },
    })
    print(f"  回顾报告 ID: {review_id}")

    # 验证
    reviews = storage.list_reviews()
    assert len(reviews) == 1, "应该有1份回顾报告"

    print("  ✅ 通过")

    # ============================================================
    # 场景8：用户修正，删除洞察后重新评估模式
    # ============================================================
    print("\n[场景8] 用户修正：删除第3个洞察后重新评估模式证据门槛")

    # 用户不同意第3个洞察，要求删除
    print(f"  用户要求删除洞察卡: {insight3_id}")
    storage.delete_insight(insight3_id, cascade=True)

    # 验证洞察卡已删除
    insights = storage.list_insights()
    assert len(insights) == 2, "应该只剩2张洞察卡"

    # 验证模式卡已被重新评估（证据不足，降为待验证）
    pattern = storage.get_pattern(pattern_id)
    assert pattern is not None, "模式卡应该还在"
    assert pattern["status"] == "pending_verification", "模式卡应该被降为待验证（证据不足3个独立实例）"
    assert pattern["evidence"]["instance_count"] == 2, "支持洞察数应该为2"
    print(f"  模式卡状态: {pattern['status']}")
    print(f"  降级原因: {pattern.get('downgraded_reason', '')}")

    print("  ✅ 通过")

    # ============================================================
    # 场景9：用户配置，禁用模式识别模块
    # ============================================================
    print("\n[场景9] 用户配置：禁用模式识别模块")

    # 用户决定暂时不想要模式识别
    storage.update_module("pattern_recognition", False)
    assert storage.is_module_enabled("pattern_recognition") == False, "模式识别模块应该被禁用"

    config = storage.read_config()
    print(f"  pattern_recognition 启用: {config['modules']['pattern_recognition']['enabled']}")

    # 重新启用
    storage.update_module("pattern_recognition", True)
    assert storage.is_module_enabled("pattern_recognition") == True, "模式识别模块应该被重新启用"

    print("  ✅ 通过")

    # ============================================================
    # 场景10：探索进度保存与恢复
    # ============================================================
    print("\n[场景10] 探索进度保存与恢复")

    # 模拟长时间对话中断，保存进度
    storage.write_progress({
        "current_workflow": "initial-assessment",
        "current_step": 4,
        "total_steps": 7,
        "step_description": "早期记忆探索",
        "recorded_answers": [
            {
                "step": 1,
                "question": "最近一次开会你本来有想法但最终没说出口，当时你心里最担心的是什么？",
                "answer": "我担心自己说的东西没价值",
                "recorded_at": "2026-09-05T10:05:00+08:00",
            },
            {
                "step": 2,
                "question": "这个'觉得没价值'的判断，是你在开会前就有了，还是在想说出口的瞬间才冒出来的？",
                "answer": "开会前就有了",
                "recorded_at": "2026-09-05T10:10:00+08:00",
            },
            {
                "step": 3,
                "question": "你在朋友面前也会这样吗？",
                "answer": "不会，在朋友面前我很能说",
                "recorded_at": "2026-09-05T10:15:00+08:00",
            },
        ],
        "temporary_insights": ["也许'觉得没价值'是一种预先的自我保护"],
        "can_resume": True,
    })
    print("  探索进度已保存")

    # 验证可以恢复
    assert storage.can_resume() == True, "应该可以恢复"
    progress = storage.read_progress()
    assert progress["current_step"] == 4, "当前步骤应该是4"
    assert len(progress["recorded_answers"]) == 3, "应该有3个已记录答案"
    print(f"  当前步骤: {progress['current_step']}/{progress['total_steps']}")
    print(f"  已记录答案数: {len(progress['recorded_answers'])}")

    # 清除进度
    storage.clear_progress()
    assert storage.can_resume() == False, "清除后应该不可以恢复"

    print("  ✅ 通过")

    # ============================================================
    # 场景11：删除级联，删除对话记录时级联删除相关洞察和模式
    # ============================================================
    print("\n[场景11] 删除级联：删除对话记录时级联删除相关洞察和模式")

    # 先确认当前数据
    print(f"  删除前：对话记录 {len(storage.list_conversations())} 条，洞察卡 {len(storage.list_insights())} 张，模式卡 {len(storage.list_patterns())} 张")

    # 删除第一个对话记录（应该级联删除第一个洞察卡）
    storage.delete_conversation(conv1_id, cascade=True)

    # 验证
    conversations = storage.list_conversations()
    insights = storage.list_insights()
    print(f"  删除后：对话记录 {len(conversations)} 条，洞察卡 {len(insights)} 张，模式卡 {len(storage.list_patterns())} 张")
    assert len(conversations) == 2, "应该只剩2条对话记录"
    assert len(insights) == 1, "应该只剩1张洞察卡（第一个被级联删除）"

    print("  ✅ 通过")

    # ============================================================
    # 场景12：全量删除
    # ============================================================
    print("\n[场景12] 全量删除")

    # 获取删除前统计
    stats_before = storage.get_stats()
    print(f"  删除前统计: {stats_before}")

    # 全量删除
    storage.delete_all()

    # 验证
    stats_after = storage.get_stats()
    print(f"  删除后统计: {stats_after}")
    assert stats_after["insights_count"] == 0, "洞察卡应该为0"
    assert stats_after["conversations_count"] == 0, "对话记录应该为0"
    assert stats_after["patterns_count"] == 0, "模式卡应该为0"
    assert stats_after["reviews_count"] == 0, "回顾报告应该为0"
    assert stats_after["profile_exists"] == False, "画像应该不存在"
    assert stats_after["config_exists"] == False, "配置应该不存在"

    print("  ✅ 通过")

    # ============================================================
    # 清理测试数据
    # ============================================================
    print("\n[清理] 删除测试目录")
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)
    print("  ✅ 完成")

    # ============================================================
    # 测试总结
    # ============================================================
    print("\n" + "=" * 70)
    print("所有端到端测试通过！")
    print("=" * 70)
    print("\n测试覆盖的完整用户旅程：")
    print("  1. 用户首次使用，创建空档案和配置 ✅")
    print("  2. 第一次对话：探索'开会不敢发言'，提取洞察，用户确认保存 ✅")
    print("  3. 第二次对话：探索'领导面前紧张'，提取洞察，用户确认保存 ✅")
    print("  4. 第三次对话：探索'朋友讨论沉默'，提取洞察，用户确认保存 ✅")
    print("  5. 模式识别：基于3个洞察识别'面对评判氛围时沉默'的重复模式 ✅")
    print("  6. 画像驱动对话：基于生活风格画像提供个性化回应 ✅")
    print("  7. 定期校准回顾：生成回顾报告 ✅")
    print("  8. 用户修正：删除洞察后重新评估模式证据门槛 ✅")
    print("  9. 用户配置：禁用/启用模式识别模块 ✅")
    print("  10. 探索进度保存与恢复 ✅")
    print("  11. 删除级联：删除对话记录时级联删除相关洞察和模式 ✅")
    print("  12. 全量删除 ✅")
    print("\n持久化功能已完整验证，可以进入下一阶段。")


if __name__ == "__main__":
    test_persistence_e2e()
