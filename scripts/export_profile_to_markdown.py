#!/usr/bin/env python3
"""
导出生活风格画像为 Markdown 文件（只导出画像，不导出对话原文）。

本脚本的唯一用途：用户说"查看画像/我的画像/生活风格画像"时，生成
画像主体 + 对话记录摘要索引（不含完整对话原文），固定文件名
`我的生活风格画像.md`，每次查看覆盖上一次。

⚠️ 重要：本脚本【不】导出完整对话档案。用户说"查看档案/查看对话/
聊天记录/完整对话原文"时，必须改用 `export_archive_to_html.py`
生成交互式 HTML 档案，禁止调用本脚本冒充档案。

将 storage/data/default/ 中的画像数据转换为直观的 Markdown 报告，
保存到 outputs/ 目录下，方便用户查看、保存和导出。

支持未加密存储（local_unencrypted）和加密存储（local_encrypted）两种模式。
密码优先从环境变量 ADLERIAN_PASSWORD 读取，严禁用 --password 明文传参。

使用方式：
    # 未加密存储
    python scripts/export_profile_to_markdown.py

    # 加密存储（通过环境变量传递密码）
    $env:ADLERIAN_PASSWORD="<密码>"; python scripts/export_profile_to_markdown.py

输出：
    outputs/我的生活风格画像.md   （画像报告，固定文件名，覆盖上一次）
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# 添加适配器路径，用于加密存储模式
_ADAPTERS_DIR = Path(__file__).resolve().parents[1] / "storage" / "adapters"
if str(_ADAPTERS_DIR) not in sys.path:
    sys.path.insert(0, str(_ADAPTERS_DIR))


def load_profile(profile_path: str) -> dict:
    """加载画像数据"""
    if not os.path.exists(profile_path):
        print(f"错误：画像文件不存在：{profile_path}")
        print("请先完成初步画像建立并保存画像。")
        sys.exit(1)
    try:
        with open(profile_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"错误：画像文件不是有效的 JSON：{e}")
        sys.exit(1)
    except Exception as e:
        print(f"错误：读取画像文件失败：{e}")
        sys.exit(1)


def format_timestamp(timestamp: str) -> str:
    """格式化时间戳"""
    if not timestamp:
        return "未知"
    try:
        dt = datetime.fromisoformat(timestamp)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return timestamp


def format_date_only(timestamp: str) -> str:
    """只格式化日期部分（用于目录和索引）"""
    if not timestamp:
        return "未知日期"
    try:
        dt = datetime.fromisoformat(timestamp)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return str(timestamp)[:10]


def get_source_status(conv: dict) -> str:
    """获取对话记录的来源状态标记"""
    ft = conv.get("full_transcript", {})
    source = ft.get("source", "")
    if source == "conversation_history":
        return "✅来源完整"
    elif source:
        return f"⚠️来源={source}"
    else:
        return "⚠️来源缺失"


# ============================================================
# 模式1：查看画像（画像主体 + 对话摘要索引）
# ============================================================

def generate_profile_markdown(profile: dict, conversations: list = None) -> str:
    """
    生成"查看画像"模式的 Markdown：画像主体 + 对话记录摘要索引。
    不包含完整对话原文（完整对话请用 export_archive_to_html.py 导出交互式 HTML 档案）。
    """
    if conversations is None:
        conversations = []
    lines = []

    # 先收集各部分数据，用于生成完整目录和动态编号
    profile_status_raw = profile.get("profile_status", "")
    lifestyle_overview = profile.get("lifestyle_overview", {})
    core_dimensions = profile.get("core_dimensions", {})
    current_focus = profile.get("current_focus", {})
    confirmed_understandings = profile.get("confirmed_understandings", [])
    pending_understandings = profile.get("pending_understandings", [])
    trigger_boundaries = profile.get("trigger_boundaries", {})
    strengths_and_values = profile.get("strengths_and_values", {})
    confirmed_patterns = profile.get("confirmed_patterns", [])
    pending_core_belief_updates_all = profile.get("pending_core_belief_updates", [])
    pending_core_belief_updates = [p for p in pending_core_belief_updates_all if p.get("status") == "pending"]
    pending_conflicts_all = profile.get("pending_conflicts", [])
    pending_conflicts = [c for c in pending_conflicts_all if c.get("status") == "pending"]
    change_log = profile.get("change_log", [])

    # 兼容旧画像：如果没有 profile_status 字段，根据画像内容智能判断状态
    if not profile_status_raw:
        has_overview = bool(lifestyle_overview.get("core_summary"))
        has_dimensions = any(
            core_dimensions.get(k, {}).get("core_belief") or core_dimensions.get(k, {}).get("details")
            for k in core_dimensions
        )
        if has_overview and has_dimensions:
            profile_status = "initialized"
        elif has_dimensions:
            profile_status = "partial"
        else:
            profile_status = "not_initialized"
    else:
        profile_status = profile_status_raw

    # 维度名称映射（用于目录和标题）
    dimension_names = {
        "self_concept": ("自我概念", "self_concept", "我是谁"),
        "self_ideal": ("理想自我", "self_ideal", "我想成为谁"),
        "world_view": ("世界观", "world_view", "世界是什么样的"),
        "view_of_others": ("他人观", "view_of_others", "他人是什么样的"),
        "private_logic": ("私人逻辑", "private_logic", "生活中遵循的潜规则"),
        "basic_mistakes": ("基本错误", "basic_mistakes", "核心信念中的错误模式"),
        "behavioral_strategies": ("行为策略", "behavioral_strategies", "常用的应对方式"),
        "social_interest": ("社会兴趣", "social_interest", "对他人和共同体的关心程度"),
        "inferiority_and_compensation": ("自卑感与补偿方式", "inferiority_and_compensation", ""),
    }

    # 动态编号：先收集所有有内容的一级章节，按顺序分配连续编号
    sections = [
        ("basic_info", "基本信息", True),
        ("lifestyle_overview", "生活风格概览", bool(lifestyle_overview)),
        ("core_dimensions", "核心维度", bool(core_dimensions)),
        ("current_focus", "当前最想理解或正在变化的事", bool(current_focus and (current_focus.get("current_topic") or current_focus.get("response_preference")))),
        ("confirmed_understandings", "已确认的理解", bool(confirmed_understandings)),
        ("pending_understandings", "待验证的理解", bool(pending_understandings)),
        ("trigger_boundaries", "触发边界与回应偏好", bool(trigger_boundaries and any(trigger_boundaries.values()))),
        ("strengths_and_values", "已经存在的力量、价值与方向", bool(strengths_and_values and any(strengths_and_values.values()))),
        ("confirmed_patterns", "已达到证据门槛的重复模式", bool(confirmed_patterns)),
        ("pending_updates", "待确认的画像更新", bool(pending_core_belief_updates)),
        ("pending_conflicts", "待校正的冲突", bool(pending_conflicts)),
        ("change_log", "变更记录", bool(change_log)),
        ("conversations", "对话记录索引", bool(conversations)),
    ]

    # 给有内容的章节分配连续编号
    section_numbers = {}
    num = 0
    for key, title, has_content in sections:
        if has_content:
            num += 1
            section_numbers[key] = num

    # 标题
    lines.append("# 生活风格画像报告")
    lines.append("")
    lines.append("> 这是一份基于阿德勒心理学的生活风格画像报告，是我们共同理解你的一个起点。")
    lines.append("> 它不是对你的定义，而是暂定的工作假设，随时可以修订。")
    lines.append("> 如需查看完整对话原文，请说\"查看档案\"。")
    lines.append("")

    # 画像状态标注
    if profile_status == "partial":
        lines.append("---")
        lines.append("")
        lines.append("⚠️ **这是部分画像（Partial Profile）**")
        lines.append("")
        lines.append("你目前还没有完成系统的初步画像建立。这份画像只包含了从探索性对话中累积的零散理解，还不是完整的生活风格画像。")
        lines.append("")
        lines.append("**部分画像的限制：**")
        lines.append("- 只有部分维度有内容，其他维度还是空的")
        lines.append("- 没有生活风格概览（核心摘要、关键主题）")
        lines.append("- 基于零散对话的理解可能不够全面和准确")
        lines.append("")
        lines.append("**想建立完整画像？** 随时说\"建立初步画像\"，我们会通过家庭星座、早期记忆、当前功能等维度系统建立完整的生活风格画像。之前保存的零散理解会自动合并到新画像中，不会丢失。")
        lines.append("")
        lines.append("---")
        lines.append("")
    elif profile_status == "initialized":
        lines.append("✅ **已完成初步画像建立**")
        lines.append("")
        lines.append("这份画像是通过系统的初步画像建立工作流完成的，包含了家庭星座、早期记忆、当前功能等多个维度的综合评估。后续对话中发现的新理解会持续累积到画像中。")
        lines.append("")

    # 目录（Word风格，一级+二级，和后面的标题一一对应，只列有内容的章节）
    lines.append("## 目录")
    lines.append("")
    for key, title, has_content in sections:
        if has_content:
            n = section_numbers[key]
            lines.append(f"{n}. {title}")
            # 二级子章节
            if key == "core_dimensions":
                dim_idx = 0
                for dkey, (cn_name, en_name, subtitle) in dimension_names.items():
                    if core_dimensions.get(dkey):
                        dim_idx += 1
                        sub_title = f"{n}.{dim_idx} {cn_name}（{en_name}）"
                        if subtitle:
                            sub_title += f"：{subtitle}"
                        lines.append(f"   {sub_title}")
            elif key == "confirmed_understandings":
                for i, u in enumerate(confirmed_understandings, 1):
                    utitle = u.get('title', u.get('id', f'理解{i}'))
                    lines.append(f"   {n}.{i} U{i}：{utitle}")
            elif key == "pending_understandings":
                for i, t in enumerate(pending_understandings, 1):
                    ttitle = t.get('title', t.get('id', f'待验证{i}'))
                    lines.append(f"   {n}.{i} T{i}：{ttitle}")
            elif key == "confirmed_patterns":
                for i, p in enumerate(confirmed_patterns, 1):
                    ptitle = p.get('title', p.get('id', f'P{i}'))
                    lines.append(f"   {n}.{i} {ptitle}")
    lines.append("")
    lines.append("> 如需查看完整对话原文，请说\"查看档案\"导出交互式 HTML 档案。")
    lines.append("")
    # 基本信息
    lines.append(f"## {section_numbers['basic_info']}. 基本信息")
    lines.append("")
    lines.append(f"- **画像ID**：{profile.get('id', '未知')}")
    lines.append(f"- **创建时间**：{format_timestamp(profile.get('created_at', ''))}")
    lines.append(f"- **最近更新**：{format_timestamp(profile.get('updated_at', ''))}")
    lines.append(f"- **版本**：{profile.get('version', '未知')}")
    lines.append(f"- **来源**：{profile.get('source', '未知')}")
    lines.append("")
    # 生活风格概览
    if lifestyle_overview:
        lines.append(f"## {section_numbers['lifestyle_overview']}. 生活风格概览")
        lines.append("")
        if lifestyle_overview.get("core_summary"):
            lines.append("**核心摘要**：")
            lines.append("")
            lines.append(f"> {lifestyle_overview['core_summary']}")
            lines.append("")
        if lifestyle_overview.get("key_themes"):
            lines.append("**当前最突出的主题**：")
            lines.append("")
            for theme in lifestyle_overview["key_themes"]:
                lines.append(f"- {theme}")
            lines.append("")
        if lifestyle_overview.get("confidence"):
            lines.append(f"**置信度**：{lifestyle_overview['confidence']}")
            lines.append("")

    # 核心维度
    if core_dimensions:
        lines.append(f"## {section_numbers['core_dimensions']}. 核心维度")
        lines.append("")
        lines.append("基于阿德勒心理学的生活风格评估维度，每个维度都是暂定的、可校正的。")
        lines.append("")

        dim_idx = 0
        for key, (cn_name, en_name, subtitle) in dimension_names.items():
            dimension = core_dimensions.get(key, {})
            if dimension:
                dim_idx += 1
                title = f"### {section_numbers['core_dimensions']}.{dim_idx} {cn_name}（{en_name}）"
                if subtitle:
                    title += f"：{subtitle}"
                lines.append(title)
                lines.append("")
                if dimension.get("core_belief"):
                    lines.append(f"- **核心信念**：{dimension['core_belief']}")
                if dimension.get("confidence"):
                    lines.append(f"- **置信度**：{dimension['confidence']}")
                if dimension.get("source"):
                    lines.append(f"- **来源**：{dimension['source']}")
                if dimension.get("user_correction"):
                    lines.append(f"- **用户校正**：{dimension['user_correction']}")
                lines.append("")
                if dimension.get("details"):
                    lines.append("**细节**：")
                    lines.append("")
                    for i, detail in enumerate(dimension["details"], 1):
                        if isinstance(detail, dict):
                            content = detail.get("content", str(detail))
                            context = detail.get("context_tags", [])
                            if context:
                                lines.append(f"{i}. {content}（情境：{', '.join(context)}）")
                            else:
                                lines.append(f"{i}. {content}")
                        else:
                            lines.append(f"{i}. {detail}")
                    lines.append("")

    # 当前最想理解或正在变化的事
    if current_focus and (current_focus.get("current_topic") or current_focus.get("response_preference")):
        lines.append(f"## {section_numbers['current_focus']}. 当前最想理解或正在变化的事")
        lines.append("")
        if current_focus.get("current_topic"):
            lines.append(f"- **当前议题**：{current_focus['current_topic']}")
        if current_focus.get("response_preference"):
            lines.append(f"- **用户希望怎样被回应**：{current_focus['response_preference']}")
        if current_focus.get("last_updated"):
            lines.append(f"- **最近更新**：{format_timestamp(current_focus['last_updated'])}")
        lines.append("")

    # 已确认的理解
    if confirmed_understandings:
        lines.append(f"## {section_numbers['confirmed_understandings']}. 已确认的理解")
        lines.append("")
        lines.append(f"共 {len(confirmed_understandings)} 条已确认的理解。")
        lines.append("")
        for i, understanding in enumerate(confirmed_understandings, 1):
            lines.append(f"### {section_numbers['confirmed_understandings']}.{i} U{i}：{understanding.get('title', understanding.get('id', f'理解{i}'))}")
            lines.append("")
            if understanding.get("user_expression"):
                lines.append(f"**用户明确表达**：{understanding['user_expression']}")
                lines.append("")
            if understanding.get("shared_summary"):
                lines.append(f"**共同整理**：{understanding['shared_summary']}")
                lines.append("")
            if understanding.get("applicable_contexts"):
                lines.append(f"**适用情境与例外**：{understanding['applicable_contexts']}")
                lines.append("")
            if understanding.get("evidence_and_confirmation"):
                lines.append(f"**依据与最后确认**：{understanding['evidence_and_confirmation']}")
                lines.append("")
            if understanding.get("related_dimension"):
                lines.append(f"**关联的核心维度**：{understanding['related_dimension']}")
                lines.append("")

    # 待验证的理解
    if pending_understandings:
        lines.append(f"## {section_numbers['pending_understandings']}. 待验证的理解")
        lines.append("")
        lines.append(f"共 {len(pending_understandings)} 条待验证的理解。")
        lines.append("")
        for i, understanding in enumerate(pending_understandings, 1):
            lines.append(f"### {section_numbers['pending_understandings']}.{i} T{i}：{understanding.get('title', understanding.get('id', f'待验证{i}'))}")
            lines.append("")
            if understanding.get("user_material"):
                lines.append(f"**用户明确材料**：{understanding['user_material']}")
                lines.append("")
            if understanding.get("possible_understanding"):
                lines.append(f"**需要校正的可能理解**：{understanding['possible_understanding']}")
                lines.append("")
            if understanding.get("uncertain_parts"):
                lines.append(f"**还不确定或存在差异的部分**：{understanding['uncertain_parts']}")
                lines.append("")
            if understanding.get("confidence"):
                lines.append(f"**当前置信度**：{understanding['confidence']}")
            if understanding.get("user_choice"):
                lines.append(f"**用户的选择**：{understanding['user_choice']}")
            if understanding.get("related_dimension"):
                lines.append(f"**关联的核心维度**：{understanding['related_dimension']}")
            lines.append("")

    # 触发边界与回应偏好
    if trigger_boundaries and any(trigger_boundaries.values()):
        lines.append(f"## {section_numbers['trigger_boundaries']}. 触发边界与回应偏好")
        lines.append("")
        if trigger_boundaries.get("sensitive_topics"):
            lines.append(f"- **可能需要更谨慎的议题或触发**：{trigger_boundaries['sensitive_topics']}")
        if trigger_boundaries.get("preferred_response_style"):
            lines.append(f"- **希望的回应方式**：{trigger_boundaries['preferred_response_style']}")
        if trigger_boundaries.get("unwanted_surprises"):
            lines.append(f"- **不希望突然发生的事**：{trigger_boundaries['unwanted_surprises']}")
        if trigger_boundaries.get("support_preferences"):
            lines.append(f"- **可参考的现实支持偏好**：{trigger_boundaries['support_preferences']}")
        lines.append("")

    # 已经存在的力量、价值与方向
    if strengths_and_values and any(strengths_and_values.values()):
        lines.append(f"## {section_numbers['strengths_and_values']}. 已经存在的力量、价值与方向")
        lines.append("")
        if strengths_and_values.get("existing_strengths"):
            lines.append(f"- **已有力量或例外**：{strengths_and_values['existing_strengths']}")
        if strengths_and_values.get("values_to_keep"):
            lines.append(f"- **想守住的价值**：{strengths_and_values['values_to_keep']}")
        if strengths_and_values.get("directions_to_explore"):
            lines.append(f"- **正在尝试或愿意探索的方向**：{strengths_and_values['directions_to_explore']}")
        lines.append("")

    # 已达到证据门槛的重复模式
    if confirmed_patterns:
        lines.append(f"## {section_numbers['confirmed_patterns']}. 已达到证据门槛的重复模式")
        lines.append("")
        lines.append(f"共 {len(confirmed_patterns)} 个已确认的重复模式。")
        lines.append("")
        for i, pattern in enumerate(confirmed_patterns, 1):
            pattern_title = pattern.get('title', pattern.get('id', f'P{i}'))
            lines.append(f"### {section_numbers['confirmed_patterns']}.{i} {pattern_title}")
            lines.append("")
            if pattern.get("description"):
                lines.append(f"**暂定描述**：{pattern['description']}")
                lines.append("")
            if pattern.get("applicable_scope"):
                lines.append(f"**适用范围与例外**：{pattern['applicable_scope']}")
                lines.append("")
            if pattern.get("user_correction"):
                lines.append(f"**用户校正**：{pattern['user_correction']}")
                lines.append("")
            if pattern.get("status"):
                lines.append(f"**当前状态**：{pattern['status']}")
                lines.append("")
            if pattern.get("related_dimension"):
                lines.append(f"**关联的核心维度**：{pattern['related_dimension']}")
                lines.append("")

    # 待确认的画像更新（D模块：核心信念变更需用户确认）
    pending_updates = profile.get("pending_core_belief_updates", [])
    pending_updates_active = [p for p in pending_updates if p.get("status") == "pending"]
    if pending_updates_active:
        lines.append(f"## {section_numbers['pending_updates']}. 待确认的画像更新")
        lines.append("")
        lines.append(f"共 {len(pending_updates_active)} 项待确认的核心信念更新。这些是从日常对话中发现的、与你当前核心信念有差异的新理解，需要你确认后才会更新到画像中。")
        lines.append("")
        lines.append("> 你可以说\"查看待确认项\"或\"更新画像\"来处理这些更新。处理方式：接受新理解 / 保留旧理解 / 两者都保留（标注情境差异）/ 自己修正。")
        lines.append("")
        for i, item in enumerate(pending_updates_active, 1):
            dim_name = item.get("dimension_name", item.get("dimension", "未知维度"))
            lines.append(f"### 待确认项 {i}：{dim_name}")
            lines.append("")
            if item.get("old_belief"):
                lines.append(f"**当前核心信念**：{item['old_belief']}")
                lines.append("")
            if item.get("new_belief"):
                lines.append(f"**建议的新理解**：{item['new_belief']}")
                lines.append("")
            if item.get("context_tags"):
                lines.append(f"**情境标签**：{', '.join(item['context_tags'])}")
                lines.append("")
            lines.append(f"**发现时间**：{format_timestamp(item.get('created_at', ''))}")
            lines.append("")

    # 待校正的冲突（D模块：情境差异 vs 真矛盾）
    pending_conflicts = profile.get("pending_conflicts", [])
    pending_conflicts_active = [c for c in pending_conflicts if c.get("status") == "pending"]
    if pending_conflicts_active:
        lines.append(f"## {section_numbers['pending_conflicts']}. 待校正的冲突")
        lines.append("")
        lines.append(f"共 {len(pending_conflicts_active)} 项待校正的冲突。这些是新对话中发现的、与画像中已有理解存在差异的内容，需要你判断是\"不同情境下的不同表现\"还是\"真正的矛盾\"。")
        lines.append("")
        for i, item in enumerate(pending_conflicts_active, 1):
            dim_name = item.get("dimension_name", item.get("dimension", "未知维度"))
            conflict_type = item.get("conflict_type", "true_conflict")
            type_label = "情境差异（不同情境下的不同表现）" if conflict_type == "context_difference" else "真矛盾（同一情境下观点相反）"
            lines.append(f"### 冲突 {i}：{dim_name}")
            lines.append("")
            lines.append(f"**冲突类型**：{type_label}")
            lines.append("")
            if item.get("old_understanding"):
                lines.append(f"**已有理解**：{item['old_understanding']}")
                lines.append("")
            if item.get("new_understanding"):
                lines.append(f"**新理解**：{item['new_understanding']}")
                lines.append("")
            if item.get("context_tags"):
                lines.append(f"**情境标签**：{', '.join(item['context_tags'])}")
                lines.append("")
            lines.append(f"**发现时间**：{format_timestamp(item.get('created_at', ''))}")
            lines.append("")

    # 变更记录
    change_log = profile.get("change_log", [])
    if change_log:
        lines.append(f"## {section_numbers['change_log']}. 变更记录")
        lines.append("")
        for change in reversed(change_log):
            date = change.get("date", "未知")
            change_type = change.get("change_type", "未知")
            user_modification = change.get("user_modification", "")
            processing_notes = change.get("processing_notes", "")
            lines.append(f"- **{date}** [{change_type}]：{user_modification}")
            if processing_notes:
                lines.append(f"  - 处理说明：{processing_notes}")
        lines.append("")

    # 对话记录摘要索引（画像模式只给索引，不给全文）
    if conversations:
        lines.append(f"## {section_numbers['conversations']}. 对话记录索引")
        lines.append("")
        lines.append(f"共 {len(conversations)} 次对话记录（按时间正序，最新在最下方）。")
        lines.append("")
        lines.append("| # | 日期 | 主题 | 条数 | 来源 | 关联洞察 |")
        lines.append("|---|------|------|------|------|----------|")
        for i, conv in enumerate(conversations, 1):
            date = format_date_only(conv.get("created_at", ""))
            summary = conv.get("summary", "无摘要")
            if len(summary) > 30:
                summary = summary[:30] + "…"
            msg_count = conv.get("full_transcript", {}).get("message_count", 0)
            source_status = get_source_status(conv)
            insight_count = len(conv.get("related_insights", []))
            insight_str = f"{insight_count}条" if insight_count else "-"
            lines.append(f"| {i} | {date} | {summary} | {msg_count} | {source_status} | {insight_str} |")
        lines.append("")
        lines.append("> 如需查看某段对话的完整逐字原文，请说\"查看档案\"导出完整对话记录。")
        lines.append("")

    # 页脚
    lines.append("---")
    lines.append("")
    lines.append("*本报告由阿德勒式自我探索 Skill 自动生成。*")
    lines.append("*画像是暂定的工作假设，不是对你的定义。你可以随时查看、修改、删除任何内容。*")
    lines.append("")

    return "\n".join(lines)


# ============================================================
# 主函数
# ============================================================

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="导出生活风格画像为 Markdown 格式")
    parser.add_argument("--mode", type=str, default="profile",
                        choices=["profile"],
                        help="导出模式：profile=导出画像（含对话摘要索引）")
    args = parser.parse_args()

    # 密码优先从环境变量读取（安全方式），其次才用命令行参数
    password = os.environ.get("ADLERIAN_PASSWORD")

    # 项目根目录
    project_root = Path(__file__).resolve().parents[1]

    # 数据文件路径
    profile_path = project_root / "storage" / "data" / "default" / "profile.json"
    auth_path = project_root / "storage" / "data" / "default" / "auth.json"
    conversations_dir = project_root / "storage" / "data" / "default" / "conversations"

    # 输出目录
    output_dir = project_root / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print(f"导出模式：{args.mode}")
    print("=" * 60)
    print()

    # 检测存储模式
    is_encrypted = auth_path.exists()
    storage_mode = "加密存储 (local_encrypted)" if is_encrypted else "未加密存储 (local_unencrypted)"
    print(f"存储模式：{storage_mode}")
    print()

    # 加密适配器
    encrypted_adapter = None
    if is_encrypted:
        if not password:
            print("错误：检测到加密存储，但未提供密码。")
            print("推荐通过环境变量提供密码，例如：")
            print("  $env:ADLERIAN_PASSWORD=\"<密码>\"; python scripts/export_profile_to_markdown.py")
            sys.exit(1)
        try:
            from local_encrypted import LocalEncryptedStorageAdapter
            encrypted_adapter = LocalEncryptedStorageAdapter(
                base_dir=str(project_root / "storage" / "data"),
                user_id="default",
                password=password,
            )
            print("密码验证成功")
        except Exception as e:
            print(f"错误：密码验证失败或加密适配器初始化失败：{e}")
            sys.exit(1)
        print()

    # 读取对话记录（画像模式需要对话摘要索引，不含原文）
    print("正在读取对话记录...")
    conversations = []
    if conversations_dir.exists():
        for conv_file in conversations_dir.glob("*.json"):
            try:
                if encrypted_adapter:
                    conv_data = encrypted_adapter._read_json(conv_file)
                else:
                    with open(conv_file, "r", encoding="utf-8") as f:
                        conv_data = json.load(f)
                if conv_data and not conv_data.get("deleted", False):
                    conversations.append(conv_data)
            except Exception as e:
                print(f"  警告：读取对话记录 {conv_file.name} 失败：{e}")
        # 按创建时间正序（最早在最上方，最新在最下方）
        conversations.sort(key=lambda x: x.get("created_at", ""))
    print(f"  读取到 {len(conversations)} 次对话记录")
    print()

    generated_files = []

    # 模式：导出画像
    if args.mode == "profile":
        print("正在生成画像报告...")
        if encrypted_adapter:
            profile = encrypted_adapter._read_json(profile_path)
            if profile is None:
                print("错误：画像文件解密失败或不存在。")
                sys.exit(1)
        else:
            profile = load_profile(str(profile_path))

        markdown_content = generate_profile_markdown(profile, conversations)
        # 固定文件名，每次查看覆盖上一次，outputs/ 目录不会积累大量历史文件
        output_filename = "我的生活风格画像.md"
        output_path = output_dir / output_filename
        tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(markdown_content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, output_path)
        generated_files.append(str(output_path))
        print(f"  画像报告已保存：{output_path}")
        print()


    # 完成
    print("=" * 60)
    print("导出完成")
    print("=" * 60)
    for f in generated_files:
        print(f"  - {f}")
    print()
    print("你可以直接打开这些 Markdown 文件查看，")
    print("也可以将其转换为 Word/PDF 格式保存或分享。")
    print()


if __name__ == "__main__":
    main()
