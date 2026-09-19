#!/usr/bin/env python3
"""验证本 Skill 的结构契约：入口文件、路由分支、跨文件链接、工作流完整性、模板结构。"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# 确保在 Windows 默认 GBK 终端下也能正确输出 Unicode 字符（如 ✅）
# 避免 UnicodeEncodeError 导致脚本误报失败
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        # 对于不支持 reconfigure 的旧版本 Python，使用 io.TextIOWrapper 包装
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


ROOT = Path(__file__).resolve().parents[1]
NON_PRODUCT_MARKDOWN_FILES = {"COLLAB.md"}

# === 原有检查配置 ===
REQUIRED_FILES = (
    "SKILL.md",
    "workflows/route-and-compose.md",
    "workflows/safety-response.md",
    "workflows/initial-assessment.md",
    "workflows/exploration-response.md",
)
REQUIRED_ROUTER_LABELS = (
    "即时危险分流",
    "确认探索意愿",
    "跨时间模式识别",
)
RETIRED_WORKFLOWS = (
    "workflows/quick-vent.md",
    "workflows/reflection-prompt.md",
)

# === 新增检查配置 ===
# 工作流必需章节关键词（任一匹配即视为该维度存在）
WORKFLOW_TRIGGER_KEYWORDS = ("触发", "进入条件", "何时使用", "启动条件")
WORKFLOW_STEPS_KEYWORDS = ("步骤", "执行", "流程", "操作", "怎么做", "结构", "拍", "阶段")
WORKFLOW_OUTPUT_KEYWORDS = ("输出", "产物", "结果", "返回", "生成")
WORKFLOW_EXCEPTION_KEYWORDS = ("异常", "边界", "分支", "注意", "禁止", "限制")

# 外部链接前缀（不检查存在性）
EXTERNAL_LINK_PREFIXES = ("http://", "https://", "mailto:", "tel:", "#")

# === 打包预检（--package-check）配置：跨平台分发前才应清零 ===
# 运行时文档里不允许出现的本地绝对路径（如 C:\Users\<某人>\...）
PACKAGE_ABS_PATH_PATTERN = re.compile(r"[A-Za-z]:[\\/]Users[\\/]")
# 运行时文档里不允许出现的某一宿主专有工具/API 名（其他平台没有这些；
# 注意不列 "doubao"——本 Skill 的目标运行环境是豆包，它是合法平台名）
PACKAGE_HOST_TOOL_NAMES = (
    "present_files",
    "im_get_conversation_messages",
    "im_get_messages",
    "computer_use_tool",
    "interaction.request_action",
    "seed_browser_use",
    "seed_computer_use",
)
# 运行时文档范围（开发资产 AGENTS/docs/tests/scripts 不上运行包，不查）
PACKAGE_RUNTIME_DIRS = ("workflows", "templates", "references", "storage")

# 收集所有失败信息
failures: list[str] = []
warnings: list[str] = []


def add_failure(message: str) -> None:
    failures.append(message)


def add_warning(message: str) -> None:
    warnings.append(message)


# ============================================================
# 第一组：原有检查（入口文件、路由分支、已废弃文件）
# ============================================================

def check_required_files() -> None:
    """检查必需文件是否存在。"""
    for relative_path in REQUIRED_FILES:
        if not (ROOT / relative_path).is_file():
            add_failure(f"缺少运行所需文件：{relative_path}")


def check_retired_workflows() -> None:
    """检查已废弃工作流是否已删除。"""
    for relative_path in RETIRED_WORKFLOWS:
        if (ROOT / relative_path).exists():
            add_failure(f"已废弃工作流仍存在：{relative_path}")


def check_skill_frontmatter() -> None:
    """检查 SKILL.md 的 frontmatter 和基本字段。"""
    skill_path = ROOT / "SKILL.md"
    if not skill_path.is_file():
        return  # 已在必需文件检查中报告
    skill_text = skill_path.read_text(encoding="utf-8")
    if not skill_text.startswith("---\n"):
        add_failure("SKILL.md 缺少 YAML frontmatter")
    if "name: adlerian-self-exploration" not in skill_text:
        add_failure("SKILL.md 的 skill 名称不正确")
    if "description:" not in skill_text:
        add_failure("SKILL.md 缺少供宿主发现的 description")
    if "[路由与回应组装工作流](workflows/route-and-compose.md)" not in skill_text:
        add_failure("主入口没有指向唯一运行路由")
    if "快速倾诉" in skill_text or "简短回看" in skill_text:
        add_failure("主入口仍包含已废弃的泛倾诉或简短回看路径")


def check_router_labels() -> None:
    """检查路由工作流是否包含核心分支标签。"""
    router_path = ROOT / "workflows/route-and-compose.md"
    if not router_path.is_file():
        return
    router_text = router_path.read_text(encoding="utf-8")
    for label in REQUIRED_ROUTER_LABELS:
        if label not in router_text:
            add_failure(f"路由缺少核心分支：{label}")
    if "quick-vent.md" in router_text or "reflection-prompt.md" in router_text:
        add_failure("路由仍指向已废弃工作流")


# ============================================================
# 第二组：跨文件引用链接检查
# ============================================================

def find_markdown_files() -> list[Path]:
    """递归查找产品 Markdown（排除协作记录、.git、运行时数据和输出）。"""
    md_files: list[Path] = []
    for path in ROOT.rglob("*.md"):
        # 排除 .git 目录
        if ".git" in path.parts:
            continue
        if path.relative_to(ROOT).as_posix() in NON_PRODUCT_MARKDOWN_FILES:
            continue
        # 排除 storage/data 目录（运行时生成的用户数据）
        rel_parts = path.relative_to(ROOT).parts
        if "storage" in rel_parts and "data" in rel_parts:
            # 检查是否是 storage/data 路径
            try:
                storage_idx = rel_parts.index("storage")
                if storage_idx + 1 < len(rel_parts) and rel_parts[storage_idx + 1] == "data":
                    continue
            except ValueError:
                pass
        # 排除 outputs 目录（运行时生成）
        if "outputs" in rel_parts:
            continue
        md_files.append(path)
    return md_files


def extract_markdown_links(text: str) -> list[str]:
    """从 markdown 文本中提取所有链接路径。"""
    # 匹配 [text](url) 格式
    pattern = r"\[([^\]]*)\]\(([^)]+)\)"
    links = re.findall(pattern, text)
    return [url for _, url in links]


def is_external_link(url: str) -> bool:
    """判断是否为外部链接或锚点链接。"""
    url = url.strip()
    for prefix in EXTERNAL_LINK_PREFIXES:
        if url.startswith(prefix):
            return True
    return False


def check_cross_file_links() -> None:
    """检查所有 .md 文件中的相对链接是否指向存在的文件。"""
    md_files = find_markdown_files()
    total_links = 0
    broken_links = 0

    for md_file in md_files:
        text = md_file.read_text(encoding="utf-8")
        links = extract_markdown_links(text)
        relative_md = md_file.relative_to(ROOT)

        for link in links:
            link = link.strip()
            if is_external_link(link):
                continue
            # 去掉锚点部分
            link_path = link.split("#")[0].strip()
            if not link_path:
                continue  # 纯锚点链接
            total_links += 1

            # 基于当前文件所在目录解析相对路径
            target = (md_file.parent / link_path).resolve()
            try:
                target.relative_to(ROOT)
            except ValueError:
                add_failure(f"链接越出项目根目录：{relative_md} -> {link}")
                broken_links += 1
                continue

            if not target.exists():
                add_failure(f"失效链接：{relative_md} -> {link}（目标不存在）")
                broken_links += 1

    if total_links == 0:
        add_warning("未找到任何跨文件链接")
    elif broken_links == 0:
        pass  # 全部有效，无需报告


# ============================================================
# 第二组补充：代码样式路径检查 + 锚点检查
# ============================================================

# 运行时会被加载的目录（AGENTS/docs/tests 等开发文档允许引用已废弃项，不纳入本检查）
RUNTIME_SCAN_DIRS = ("workflows", "templates", "references", "storage")
# 反引号包裹的代码样式相对路径，如 `templates/使用手册.md`
INLINE_PATH_PATTERN = re.compile(
    r"`((?:workflows|templates|storage|scripts|references|docs|tests|examples)/"
    r"[A-Za-z0-9_\-一-龥/]+\.(?:md|py|json|txt|html))`"
)
# 命中这些标记的行属于"已废弃/历史说明"语境，其中缺失的路径不报错
RETIRED_CONTEXT_MARKERS = ("~~", "已废弃", "已删除", "曾为", "不再使用", "历史")
# 这些目录由 Skill 在首次使用或导出时创建，不应要求作为发布包内的静态文件存在。
RUNTIME_GENERATED_PATH_PREFIXES = ("storage/data/", "outputs/")


def _is_runtime_doc(md_file: Path) -> bool:
    """是否为运行时实际加载的文档（SKILL/README 与运行时目录）；开发文档不查代码样式路径。"""
    rel = md_file.relative_to(ROOT)
    if rel.name in ("SKILL.md", "README.md"):
        return True
    return bool(rel.parts) and rel.parts[0] in RUNTIME_SCAN_DIRS


def _is_runtime_generated_path(relative_path: str) -> bool:
    """判断路径是否为首次使用或导出时生成的运行时产物。"""
    normalized = relative_path.replace("\\", "/")
    return normalized.startswith(RUNTIME_GENERATED_PATH_PREFIXES)


def check_inline_code_paths() -> None:
    """检查反引号包裹的代码样式相对路径是否真实存在。

    markdown 链接检查只覆盖 [text](path)，覆盖不到反引号路径；本函数堵住该盲区，
    防止出现 first-use.md 引用已改名的 welcome-guide.md 这类运行时死链。
    """
    for md_file in find_markdown_files():
        if not _is_runtime_doc(md_file):
            continue
        relative_md = md_file.relative_to(ROOT)
        for idx, line in enumerate(md_file.read_text(encoding="utf-8").splitlines(), 1):
            if any(marker in line for marker in RETIRED_CONTEXT_MARKERS):
                continue
            for raw in INLINE_PATH_PATTERN.findall(line):
                rel_path = raw.strip().split("#")[0]
                if _is_runtime_generated_path(rel_path):
                    continue
                if (md_file.parent / rel_path).exists() or (ROOT / rel_path).exists():
                    continue
                add_failure(f"代码样式路径不存在：{relative_md}:L{idx} -> `{raw}`（目标文件缺失）")


def _heading_slug(heading: str) -> str:
    """把 markdown 标题转成接近 GitHub 的锚点 slug（保留中文、空格转-、去标点、转小写）。"""
    slug = re.sub(r"^#+\s*", "", heading.strip().lower())
    slug = re.sub(r"[，。、：；！？·.,:;!?\"'（）()\[\]{}<>《》「」“”‘’/\\|*#`~@$%^&+=]+", "", slug)
    slug = re.sub(r"\s+", "-", slug)
    return slug


def _collect_slugs(path: Path) -> set:
    slugs = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("#"):
            slugs.add(_heading_slug(line.lstrip()))
    return slugs


def check_markdown_anchors() -> None:
    """检查 [text](xxx.md#anchor) 与同文件 (#anchor) 的锚点是否能在目标标题中找到。"""
    for md_file in find_markdown_files():
        text = md_file.read_text(encoding="utf-8")
        relative_md = md_file.relative_to(ROOT)
        own_slugs = _collect_slugs(md_file)
        for idx, line in enumerate(text.splitlines(), 1):
            for url in re.findall(r"\]\(([^)]+)\)", line):
                url = url.strip()
                if url.startswith(EXTERNAL_LINK_PREFIXES) or "#" not in url:
                    continue
                path_part, _, anchor = url.partition("#")
                anchor = anchor.strip()
                if not anchor:
                    continue
                if not path_part:  # 纯同文件锚点
                    if anchor not in own_slugs:
                        add_failure(f"失效锚点：{relative_md}:L{idx} -> #{anchor}（当前文件无此标题）")
                    continue
                target = (md_file.parent / path_part).resolve()
                if not target.exists():
                    continue  # 文件缺失由跨文件链接检查负责，不重复报
                if anchor not in _collect_slugs(target):
                    add_failure(f"失效锚点：{relative_md}:L{idx} -> {url}（目标文件无对应标题）")


def check_package_readiness() -> None:
    """打包预检（仅 --package-check 触发）：运行时文档不得含本地绝对路径或宿主专有工具名。

    这些耦合点在本地开发版是正确实现，因此默认检查不查；跨平台分发前跑本检查，
    把本地耦合点全部揪出来，确保运行包平台中立。开发资产（AGENTS/docs/tests/scripts）不上运行包，不查。
    """
    for md_file in find_markdown_files():
        rel = md_file.relative_to(ROOT)
        in_runtime = rel.name == "SKILL.md" or (
            bool(rel.parts) and rel.parts[0] in PACKAGE_RUNTIME_DIRS
        )
        if not in_runtime:
            continue
        for idx, line in enumerate(md_file.read_text(encoding="utf-8").splitlines(), 1):
            if PACKAGE_ABS_PATH_PATTERN.search(line):
                add_failure(f"打包预检：{rel}:L{idx} 含本地绝对路径 -> {line.strip()[:80]}")
            for tool in PACKAGE_HOST_TOOL_NAMES:
                if tool in line:
                    add_failure(f"打包预检：{rel}:L{idx} 含宿主专有工具/API 名 '{tool}'")
                    break  # 同一行只报一次，避免刷屏


# ============================================================
# 第三组：工作流章节完整性检查
# ============================================================

def check_workflow_completeness() -> None:
    """检查 workflows/ 下每个工作流是否包含必需章节。"""
    workflows_dir = ROOT / "workflows"
    if not workflows_dir.is_dir():
        add_failure("workflows/ 目录不存在")
        return

    for wf_file in sorted(workflows_dir.glob("*.md")):
        if wf_file.name == "README.md":
            continue  # 模块说明文件不检查工作流结构
        text = wf_file.read_text(encoding="utf-8")
        relative = wf_file.relative_to(ROOT)
        missing: list[str] = []

        if not any(kw in text for kw in WORKFLOW_TRIGGER_KEYWORDS):
            missing.append("触发/进入条件")
        if not any(kw in text for kw in WORKFLOW_STEPS_KEYWORDS):
            missing.append("执行步骤")
        if not any(kw in text for kw in WORKFLOW_OUTPUT_KEYWORDS):
            missing.append("输出/产物")
        if not any(kw in text for kw in WORKFLOW_EXCEPTION_KEYWORDS):
            missing.append("异常/边界处理")

        if missing:
            add_failure(f"工作流缺少必需章节：{relative} -> 缺少：{', '.join(missing)}")


# ============================================================
# 第四组：SKILL.md 引用完整性检查
# ============================================================

def check_skill_references() -> None:
    """检查 SKILL.md 中引用的所有文件是否存在。"""
    skill_path = ROOT / "SKILL.md"
    if not skill_path.is_file():
        return
    text = skill_path.read_text(encoding="utf-8")
    links = extract_markdown_links(text)

    for link in links:
        link = link.strip()
        if is_external_link(link):
            continue
        link_path = link.split("#")[0].strip()
        if not link_path:
            continue
        target = (skill_path.parent / link_path).resolve()
        if not target.exists():
            add_failure(f"SKILL.md 引用失效：{link}（目标不存在）")


# ============================================================
# 第五组：模板基本结构检查
# ============================================================

def check_template_structure() -> None:
    """检查 templates/ 下每个模板是否非空且有基本 markdown 结构。"""
    templates_dir = ROOT / "templates"
    if not templates_dir.is_dir():
        add_failure("templates/ 目录不存在")
        return

    template_files = list(templates_dir.glob("*.md"))
    if not template_files:
        add_warning("templates/ 目录下没有 .md 模板文件")
        return

    for tpl_file in sorted(template_files):
        text = tpl_file.read_text(encoding="utf-8").strip()
        relative = tpl_file.relative_to(ROOT)

        if not text:
            add_failure(f"模板为空：{relative}")
            continue
        if not text.startswith("#"):
            add_warning(f"模板缺少标题：{relative}")
        # 检查是否有基本结构（至少包含标题、列表或表格中的一种）
        has_structure = bool(re.search(r"^#|^- |^\|", text, re.MULTILINE))
        if not has_structure:
            add_warning(f"模板结构过于简单（无标题/列表/表格）：{relative}")


# ============================================================
# 主函数
# ============================================================

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="阿德勒自我探索 Skill 结构契约验证")
    parser.add_argument(
        "--package-check",
        action="store_true",
        help="打包预检：额外检查运行时文档不含本地绝对路径与宿主专有工具名（上架第三方平台前跑）",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("阿德勒自我探索 Skill — 结构契约验证")
    print("=" * 60)

    # 第一组：原有检查
    print("\n【1/5】必需文件与路由分支检查")
    check_required_files()
    check_retired_workflows()
    check_skill_frontmatter()
    check_router_labels()
    if not any("缺少运行所需文件" in f or "已废弃工作流仍存在" in f
               or "SKILL.md" in f or "路由缺少核心分支" in f or "路由仍指向已废弃" in f
               for f in failures):
        print("  PASS: 必需文件、frontmatter、路由分支均正常")

    # 第二组：跨文件链接
    print("\n【2/5】跨文件引用链接、代码路径与锚点检查")
    check_cross_file_links()
    check_inline_code_paths()
    check_markdown_anchors()
    link_failures = [
        f for f in failures
        if "失效链接" in f or "链接越出" in f
        or "代码样式路径不存在" in f or "失效锚点" in f
    ]
    if not link_failures:
        print("  PASS: 跨文件链接、反引号代码路径、锚点均有效")

    # 第三组：工作流完整性
    print("\n【3/5】工作流章节完整性检查")
    check_workflow_completeness()
    wf_failures = [f for f in failures if "工作流缺少必需章节" in f]
    if not wf_failures:
        print("  PASS: 所有工作流均包含必需章节")

    # 第四组：SKILL.md 引用
    print("\n【4/5】SKILL.md 引用完整性检查")
    check_skill_references()
    skill_ref_failures = [f for f in failures if "SKILL.md 引用失效" in f]
    if not skill_ref_failures:
        print("  PASS: SKILL.md 中所有引用均有效")

    # 第五组：模板结构
    print("\n【5/5】模板基本结构检查")
    check_template_structure()
    tpl_failures = [f for f in failures if "模板为空" in f]
    if not tpl_failures:
        print("  PASS: 所有模板均非空")

    # 可选第六组：打包预检（仅 --package-check 触发）
    if args.package_check:
        print("\n【打包预检】运行包平台中立性检查（本地绝对路径 / 宿主专有工具名）")
        check_package_readiness()
        pkg_failures = [f for f in failures if f.startswith("打包预检：")]
        if not pkg_failures:
            print("  PASS: 运行时文档未发现本地绝对路径或宿主专有工具名")
        else:
            print(f"  共 {len(pkg_failures)} 处需在上架前平台中立化（详见下方失败列表）")

    # 总结
    print("\n" + "=" * 60)
    print("验证总结")
    print("=" * 60)

    if warnings:
        print(f"\n⚠️  警告 ({len(warnings)} 项)：")
        for w in warnings:
            print(f"  - {w}")

    if failures:
        print(f"\n❌ 失败 ({len(failures)} 项)：")
        for f in failures:
            print(f"  - {f}")
        print(f"\n总计：{len(failures)} 项失败，{len(warnings)} 项警告")
        raise SystemExit(1)
    else:
        print(f"\n✅ 全部通过（{len(warnings)} 项警告）")
        print("PASS: skill entrypoint, routes, cross-file links, workflows, and templates are valid.")


if __name__ == "__main__":
    main()
