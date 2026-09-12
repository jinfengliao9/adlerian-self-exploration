#!/usr/bin/env python3
"""
D模块专项测试：画像自动累积更新 + 冲突检测

验证内容：
1. 洞察保存后自动累积到画像维度的 details（去重）
2. core_belief 变更加入待确认列表（不自动覆盖）
3. 冲突检测（情境差异 vs 真矛盾）
4. 待确认项处理（accept/keep/both/custom）
5. 冲突处理（accept_new/keep_old/context_diff/custom）
6. 画像导出包含待确认项和冲突章节
"""

import sys
import os
import glob
import shutil
from pathlib import Path

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from storage.adapters.local_json import LocalJsonStorageAdapter


def run_tests():
    test_dir = "outputs_d_test"
    test_user = "test_user_d"

    # 清理之前的测试数据
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)

    storage = LocalJsonStorageAdapter(base_dir=test_dir, user_id=test_user)

    passed = 0
    failed = 0

    def check(name, condition, detail=""):
        nonlocal passed, failed
        if condition:
            print(f"  ✅ {name}")
            passed += 1
        else:
            print(f"  ❌ {name} {detail}")
            failed += 1

    print("=" * 60)
    print("D模块专项测试：画像自动累积更新 + 冲突检测")
    print("=" * 60)

    # ---- 测试1：初始化画像，设置一个核心维度的 core_belief ----
    print("\n[测试1] 初始化画像，设置核心维度 core_belief")
    profile = storage.read_profile()
    profile["core_dimensions"]["behavioral_strategies"]["core_belief"] = "在权威人物面前会紧张，倾向于沉默"
    profile["core_dimensions"]["behavioral_strategies"]["confidence"] = "中"
    profile["core_dimensions"]["behavioral_strategies"]["source"] = "初步画像"
    storage.write_profile(profile)
    check("画像初始化成功", profile["core_dimensions"]["behavioral_strategies"]["core_belief"] != "")

    # ---- 测试2：保存洞察，自动累积 details ----
    print("\n[测试2] 保存洞察，自动累积到维度 details")
    insight1 = {
        "title": "开会时不敢发言",
        "content": "在团队会议中，当领导在场时，用户会提前准备好发言内容但最终选择沉默，担心说错话被评判。",
        "related_dimensions": ["behavioral_strategies"],
        "context_tags": ["work"],
        "confidence": "高",
        "user_confirmed": True,
    }
    insight_id1 = storage.append_insight(insight1)
    check("洞察保存成功", insight_id1 is not None)

    # 读取画像，检查 details 是否自动追加
    profile_after = storage.read_profile()
    details = profile_after["core_dimensions"]["behavioral_strategies"]["details"]
    check("details 自动追加了1条", len(details) == 1, f"实际 {len(details)} 条")
    if details:
        check("details 内容包含洞察标题", "开会时不敢发言" in details[0].get("content", ""))
        check("details 带情境标签", details[0].get("context_tags") == ["work"])
        check("details 带来源洞察ID", details[0].get("source_insight_id") == insight_id1)

    # ---- 测试3：重复洞察不重复追加（去重）----
    print("\n[测试3] 重复内容不重复追加（去重）")
    insight_dup = {
        "title": "开会时不敢发言",
        "content": "在团队会议中，当领导在场时，用户会提前准备好发言内容但最终选择沉默，担心说错话被评判。",
        "related_dimensions": ["behavioral_strategies"],
        "context_tags": ["work"],
        "confidence": "高",
        "user_confirmed": True,
    }
    storage.append_insight(insight_dup)
    profile_dup = storage.read_profile()
    details_dup = profile_dup["core_dimensions"]["behavioral_strategies"]["details"]
    check("重复内容未追加（仍为1条）", len(details_dup) == 1, f"实际 {len(details_dup)} 条")

    # ---- 测试4：新洞察建议更新 core_belief，加入待确认列表（不自动覆盖）----
    print("\n[测试4] core_belief 变更加入待确认列表（不自动覆盖）")
    insight2 = {
        "title": "在熟悉朋友面前能自由表达",
        "content": "在和熟悉的朋友单独聊天时，用户能够自由表达自己的观点，甚至会主动开玩笑，与在权威面前的沉默形成鲜明对比。",
        "related_dimensions": ["behavioral_strategies"],
        "context_tags": ["social"],
        "confidence": "高",
        "user_confirmed": True,
        "suggests_core_belief_update": True,
        "core_belief_update_content": "在权威人物面前会紧张沉默，但在熟悉安全的关系中能够自由表达",
    }
    insight_id2 = storage.append_insight(insight2)

    profile_update = storage.read_profile()
    # core_belief 不应被自动覆盖
    check("core_belief 未被自动覆盖",
          profile_update["core_dimensions"]["behavioral_strategies"]["core_belief"] == "在权威人物面前会紧张，倾向于沉默")
    # 待确认列表应有1项
    pending = profile_update.get("pending_core_belief_updates", [])
    pending_active = [p for p in pending if p.get("status") == "pending"]
    check("待确认核心信念更新有1项", len(pending_active) == 1, f"实际 {len(pending_active)} 项")
    if pending_active:
        check("待确认项维度正确", pending_active[0].get("dimension") == "behavioral_strategies")
        check("待确认项包含旧信念", "权威人物面前会紧张" in pending_active[0].get("old_belief", ""))
        check("待确认项包含新信念", "熟悉安全的关系中能够自由表达" in pending_active[0].get("new_belief", ""))

    # ---- 测试5：处理待确认项 - accept（接受新信念）----
    print("\n[测试5] 处理待确认项 - accept（接受新信念）")
    update_id = pending_active[0]["id"]
    storage.resolve_pending_core_belief_update(update_id, "accept")
    profile_accept = storage.read_profile()
    check("accept 后 core_belief 已更新",
          "熟悉安全的关系中能够自由表达" in profile_accept["core_dimensions"]["behavioral_strategies"]["core_belief"])
    pending_after = [p for p in profile_accept.get("pending_core_belief_updates", []) if p.get("status") == "pending"]
    check("待确认项已处理（不在pending状态）", len(pending_after) == 0)

    # ---- 测试6：冲突检测 - 真矛盾 ----
    print("\n[测试6] 冲突检测 - 真矛盾")
    insight3 = {
        "title": "在领导面前也能主动发言",
        "content": "在最近的一次项目汇报中，用户主动向领导提出了自己的想法，并且得到了认可，与之前在权威面前沉默的模式完全不同。",
        "related_dimensions": ["behavioral_strategies"],
        "context_tags": ["work"],
        "confidence": "高",
        "user_confirmed": True,
        "conflicts_with_existing": True,
        "conflict_type": "true_conflict",
    }
    insight_id3 = storage.append_insight(insight3)
    profile_conflict = storage.read_profile()
    conflicts = profile_conflict.get("pending_conflicts", [])
    conflicts_active = [c for c in conflicts if c.get("status") == "pending"]
    check("真矛盾加入待校正冲突列表", len(conflicts_active) == 1, f"实际 {len(conflicts_active)} 项")
    if conflicts_active:
        check("冲突类型为 true_conflict", conflicts_active[0].get("conflict_type") == "true_conflict")
        check("冲突包含已有理解", "熟悉安全的关系" in conflicts_active[0].get("old_understanding", "") or
              "权威人物面前" in conflicts_active[0].get("old_understanding", ""))

    # ---- 测试7：处理冲突 - context_diff（确认为情境差异）----
    print("\n[测试7] 处理冲突 - context_diff（确认为情境差异）")
    conflict_id = conflicts_active[0]["id"]
    storage.resolve_pending_conflict(conflict_id, "context_diff")
    profile_ctx = storage.read_profile()
    conflicts_after = [c for c in profile_ctx.get("pending_conflicts", []) if c.get("status") == "pending"]
    check("冲突已处理（不在pending状态）", len(conflicts_after) == 0)
    # 新理解应作为情境差异细节加入
    details_ctx = profile_ctx["core_dimensions"]["behavioral_strategies"]["details"]
    has_ctx_diff = any("情境差异" in (d.get("content", "") if isinstance(d, dict) else "") for d in details_ctx)
    check("新理解作为情境差异加入 details", has_ctx_diff)

    # ---- 测试8：未确认的洞察不触发画像累积 ----
    print("\n[测试8] 未确认的洞察不触发画像累积")
    insight_unconfirmed = {
        "title": "未确认的洞察",
        "content": "这是一条用户未确认的洞察，不应自动累积到画像。",
        "related_dimensions": ["self_concept"],
        "context_tags": ["self"],
        "confidence": "中",
        "user_confirmed": False,
    }
    details_before = len(storage.read_profile()["core_dimensions"]["self_concept"]["details"])
    storage.append_insight(insight_unconfirmed)
    details_after = len(storage.read_profile()["core_dimensions"]["self_concept"]["details"])
    check("未确认洞察未触发画像累积", details_before == details_after,
          f"之前 {details_before} 条，之后 {details_after} 条")

    # ---- 测试9：画像导出包含待确认项和冲突章节 ----
    print("\n[测试9] 画像导出包含待确认项和冲突章节")
    # 直接导入导出函数，构造包含待确认项和冲突的画像
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
    from export_profile_to_markdown import generate_profile_markdown

    test_profile = {
        "id": "test-profile",
        "created_at": "2026-09-10T10:00:00",
        "updated_at": "2026-09-10T12:00:00",
        "version": 3,
        "source": "test",
        "lifestyle_overview": {"core_summary": "测试画像", "key_themes": ["测试"], "confidence": "中"},
        "core_dimensions": {
            "behavioral_strategies": {
                "core_belief": "测试核心信念",
                "details": [{"content": "测试细节", "context_tags": ["work"], "created_at": "2026-09-10T10:00:00"}],
                "source": "测试",
                "confidence": "中",
            }
        },
        "pending_core_belief_updates": [
            {
                "id": "pu-001",
                "dimension": "behavioral_strategies",
                "dimension_name": "行为策略",
                "new_belief": "建议的新信念",
                "old_belief": "测试核心信念",
                "context_tags": ["social"],
                "created_at": "2026-09-10T11:00:00",
                "status": "pending",
            }
        ],
        "pending_conflicts": [
            {
                "id": "pc-001",
                "dimension": "behavioral_strategies",
                "dimension_name": "行为策略",
                "old_understanding": "已有理解",
                "new_understanding": "新理解",
                "context_tags": ["work"],
                "conflict_type": "true_conflict",
                "created_at": "2026-09-10T11:30:00",
                "status": "pending",
            }
        ],
        "change_log": [],
    }

    md_output = generate_profile_markdown(test_profile, [])
    md_lines = md_output.splitlines()
    check("导出包含目录章节", "## 目录" in md_output)
    # 章节标题带 Word 式编号（如 "## 9. 待确认的画像更新"），故按"二级标题行 + 标题文字"匹配，不写死编号
    check("导出包含待确认画像更新章节", any(ln.startswith("##") and "待确认的画像更新" in ln for ln in md_lines))
    check("导出包含待校正冲突章节", any(ln.startswith("##") and "待校正的冲突" in ln for ln in md_lines))
    check("待确认项内容正确导出", "建议的新信念" in md_output)
    check("冲突内容正确导出", "新理解" in md_output)
    check("冲突类型正确导出", "真矛盾" in md_output)

    # ---- 清理测试数据 ----
    print("\n[清理] 删除测试数据")
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)
    # 清理导出的测试文件
    for f in glob.glob(str(PROJECT_ROOT / "outputs" / "我的生活风格画像*.md")):
        try:
            os.remove(f)
        except:
            pass

    # ---- 总结 ----
    print("\n" + "=" * 60)
    print(f"测试完成：✅ 通过 {passed} 项，❌ 失败 {failed} 项")
    print("=" * 60)

    if failed > 0:
        sys.exit(1)
    else:
        print("\n🎉 D模块所有专项测试通过！")


if __name__ == "__main__":
    run_tests()
