#!/usr/bin/env python3
"""
导出完整对话档案为交互式 HTML 文件（只导出对话原文，不导出画像）

用户说"查看档案/查看对话/聊天记录"时调用本脚本；查看画像请用 export_profile_to_markdown.py。

将 storage/data/default/conversations/ 中的所有完整对话记录导出为一个
可交互的 HTML 文件，每段对话默认折叠为一行标题，点击即可展开查看完整
逐字对话原文。支持"全部展开/全部收起"按钮和目录锚点跳转。

为什么用 HTML 而不是 Markdown：
  - Markdown 的 <details> 折叠标签在豆包等平台渲染器中不被支持
  - HTML 可以用 CSS + JavaScript 实现完美的折叠交互
  - 用户在浏览器中打开即可使用，无需额外软件

支持未加密存储（local_unencrypted）和加密存储（local_encrypted）。
密码优先从环境变量 ADLERIAN_PASSWORD 读取，严禁用 --password 明文传参。

使用方式：
    # 未加密存储
    python scripts/export_archive_to_html.py

    # 加密存储（通过环境变量传递密码）
    $env:ADLERIAN_PASSWORD="<密码>"; python scripts/export_archive_to_html.py

输出：
    outputs/我的对话档案.html   （固定文件名，每次查看覆盖上一次）
"""

import argparse
import html
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# 添加适配器路径
_ADAPTERS_DIR = Path(__file__).resolve().parents[1] / "storage" / "adapters"
if str(_ADAPTERS_DIR) not in sys.path:
    sys.path.insert(0, str(_ADAPTERS_DIR))


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
    """只格式化日期部分"""
    if not timestamp:
        return "未知日期"
    try:
        dt = datetime.fromisoformat(timestamp)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return str(timestamp)[:10]


def get_source_status(conv: dict) -> tuple:
    """获取对话记录的来源状态（标记文字 + CSS类名）"""
    ft = conv.get("full_transcript", {})
    source = ft.get("source", "")
    if source == "conversation_history":
        return "✅ 来源完整", "source-ok"
    elif source:
        return f"⚠️ 来源={source}", "source-warn"
    else:
        return "⚠️ 来源缺失", "source-warn"


def escape_html(text: str) -> str:
    """转义 HTML 特殊字符，保留换行"""
    if not text:
        return ""
    return html.escape(text).replace("\n", "<br>")


def generate_html(conversations: list) -> str:
    """
    生成交互式 HTML 档案。

    结构：
    - 顶部：标题 + 说明 + 全部展开/收起按钮
    - 对话目录：可点击锚点跳转到对应对话
    - 对话列表：每段对话默认折叠（只显示一行标题），点击展开显示完整内容
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 构建对话目录和对话内容
    toc_items = []
    conversation_blocks = []

    for i, conv in enumerate(conversations, 1):
        conv_id = conv.get("id", f"conversation-{i}")
        summary = conv.get("summary", "无摘要")
        conv_type = conv.get("conversation_type", "unknown")
        created_at = format_timestamp(conv.get("created_at", ""))
        date_only = format_date_only(conv.get("created_at", ""))
        related_insights = conv.get("related_insights", [])
        related_patterns = conv.get("related_patterns", [])

        full_transcript = conv.get("full_transcript", {})
        messages = full_transcript.get("messages", []) if full_transcript.get("enabled") else []
        msg_count = len(messages)

        source_text, source_class = get_source_status(conv)

        # 折叠标题（一行）
        header_title = f"📋 对话{i}：[{date_only}] {summary[:50]}{'…' if len(summary) > 50 else ''}（{msg_count}条）{source_text}"

        # 目录项
        toc_items.append(
            f'        <li><a href="#conv-{i}" onclick="expandById(\'conv-{i}\')">'
            f'[{date_only}] {escape_html(summary[:40])}{"…" if len(summary) > 40 else ""}'
            f'（{msg_count}条）<span class="{source_class}">{source_text}</span></a></li>'
        )

        # 对话内容（展开后显示）
        meta_lines = [
            f"<p><strong>对话ID：</strong>{escape_html(conv_id)}</p>",
            f"<p><strong>对话类型：</strong>{escape_html(conv_type)}</p>",
            f"<p><strong>创建时间：</strong>{created_at}</p>",
        ]
        if related_insights:
            meta_lines.append(f"<p><strong>关联洞察：</strong>{len(related_insights)} 条</p>")
        if related_patterns:
            meta_lines.append(f"<p><strong>关联模式：</strong>{len(related_patterns)} 个</p>")

        # 来源凭证
        source_note = ""
        if messages:
            source_method = full_transcript.get("source", "")
            source_cid = full_transcript.get("source_conversation_id", "")
            pulled_at = format_timestamp(full_transcript.get("pulled_at", ""))
            if source_method == "conversation_history":
                source_note = f"✅ <strong>来源：</strong>会话历史原文（逐字保存，未经改写）"
                if source_cid:
                    source_note += f"；来源会话：{escape_html(source_cid)}"
                if pulled_at:
                    source_note += f"；拉取时间：{pulled_at}"
            else:
                source_note = "⚠️ <strong>来源凭证缺失：</strong>无法确认以下内容是否为会话历史原文，仅供参考"

        # 完整对话消息
        message_blocks = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            timestamp = format_timestamp(msg.get("timestamp", ""))

            if role == "user":
                role_label = "用户"
                msg_class = "message-user"
            elif role == "assistant":
                role_label = "Skill"
                msg_class = "message-assistant"
            else:
                role_label = role
                msg_class = "message-other"

            message_blocks.append(f'''
                <div class="message {msg_class}">
                    <div class="message-header">
                        <span class="message-role">{role_label}</span>
                        <span class="message-time">{timestamp}</span>
                    </div>
                    <div class="message-content">{escape_html(content)}</div>
                </div>''')

        if not messages:
            message_blocks.append('<p class="no-transcript">完整对话记录未保存（本次只保存了简要提取信息）。</p>')

        # 组装对话块
        block = f'''
    <div class="conversation" id="conv-{i}">
        <div class="conversation-header" onclick="toggleConversation(this)">
            <span class="conversation-title">{escape_html(header_title)}</span>
            <span class="toggle-icon">▶</span>
        </div>
        <div class="conversation-content">
            <div class="conv-meta">
                {''.join(meta_lines)}
            </div>
            <div class="conv-summary">
                <strong>摘要：</strong>
                <blockquote>{escape_html(summary)}</blockquote>
            </div>
            {"<div class='conv-source'>" + source_note + "</div>" if source_note else ""}
            <hr>
            <div class="conv-messages">
                {''.join(message_blocks)}
            </div>
        </div>
    </div>'''
        conversation_blocks.append(block)

    # 组装完整 HTML
    html_content = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>完整对话档案 - 阿德勒式自我探索</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
                         "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
            line-height: 1.7;
            color: #333;
            background: #fafafa;
            padding: 20px;
            max-width: 960px;
            margin: 0 auto;
        }}
        h1 {{
            font-size: 1.6em;
            margin-bottom: 8px;
            color: #1a1a1a;
        }}
        .subtitle {{
            color: #666;
            font-size: 0.9em;
            margin-bottom: 20px;
        }}
        .controls {{
            margin: 16px 0;
            display: flex;
            gap: 10px;
        }}
        .controls button {{
            padding: 8px 16px;
            border: 1px solid #ccc;
            border-radius: 6px;
            background: #fff;
            cursor: pointer;
            font-size: 0.9em;
            transition: background 0.2s;
        }}
        .controls button:hover {{
            background: #f0f0f0;
        }}
        h2 {{
            font-size: 1.2em;
            margin: 24px 0 12px;
            padding-bottom: 8px;
            border-bottom: 2px solid #e0e0e0;
        }}
        .toc {{
            background: #fff;
            border: 1px solid #e8e8e8;
            border-radius: 8px;
            padding: 16px 20px;
            margin-bottom: 24px;
        }}
        .toc ol {{
            padding-left: 20px;
        }}
        .toc li {{
            margin: 6px 0;
        }}
        .toc a {{
            color: #1a73e8;
            text-decoration: none;
        }}
        .toc a:hover {{
            text-decoration: underline;
        }}
        .source-ok {{
            color: #2e7d32;
            font-size: 0.85em;
        }}
        .source-warn {{
            color: #e65100;
            font-size: 0.85em;
        }}
        .conversation {{
            border: 1px solid #e0e0e0;
            border-radius: 8px;
            margin: 12px 0;
            overflow: hidden;
            background: #fff;
        }}
        .conversation-header {{
            padding: 12px 16px;
            background: #f5f5f5;
            cursor: pointer;
            display: flex;
            justify-content: space-between;
            align-items: center;
            user-select: none;
            transition: background 0.2s;
        }}
        .conversation-header:hover {{
            background: #ebebeb;
        }}
        .conversation-title {{
            font-size: 0.95em;
            font-weight: 500;
        }}
        .toggle-icon {{
            color: #888;
            font-size: 0.8em;
            transition: transform 0.2s;
        }}
        .conversation.open .toggle-icon {{
            transform: rotate(90deg);
        }}
        .conversation-content {{
            display: none;
            padding: 16px 20px;
            border-top: 1px solid #eee;
        }}
        .conversation.open .conversation-content {{
            display: block;
        }}
        .conv-meta p {{
            margin: 4px 0;
            font-size: 0.9em;
            color: #555;
        }}
        .conv-summary {{
            margin: 12px 0;
        }}
        .conv-summary blockquote {{
            border-left: 3px solid #1a73e8;
            padding: 8px 12px;
            margin: 8px 0;
            background: #f8f9ff;
            color: #444;
            font-size: 0.95em;
        }}
        .conv-source {{
            margin: 12px 0;
            padding: 10px 14px;
            border-radius: 6px;
            font-size: 0.9em;
        }}
        .conv-source:has(> div) {{
            /* fallback */
        }}
        hr {{
            border: none;
            border-top: 1px solid #eee;
            margin: 16px 0;
        }}
        .message {{
            margin: 12px 0;
            padding: 12px 16px;
            border-radius: 8px;
        }}
        .message-user {{
            background: #e8f0fe;
            border-left: 3px solid #1a73e8;
        }}
        .message-assistant {{
            background: #f5f5f5;
            border-left: 3px solid #888;
        }}
        .message-other {{
            background: #fff3e0;
            border-left: 3px solid #e65100;
        }}
        .message-header {{
            display: flex;
            justify-content: space-between;
            margin-bottom: 6px;
        }}
        .message-role {{
            font-weight: 600;
            font-size: 0.9em;
        }}
        .message-user .message-role {{ color: #1a73e8; }}
        .message-assistant .message-role {{ color: #555; }}
        .message-time {{
            color: #999;
            font-size: 0.8em;
        }}
        .message-content {{
            font-size: 0.95em;
            color: #333;
            word-break: break-word;
        }}
        .no-transcript {{
            color: #999;
            font-style: italic;
            padding: 20px;
            text-align: center;
        }}
        .footer {{
            margin-top: 32px;
            padding-top: 16px;
            border-top: 1px solid #e0e0e0;
            color: #999;
            font-size: 0.85em;
            text-align: center;
        }}
    </style>
</head>
<body>
    <h1>📚 完整对话档案</h1>
    <p class="subtitle">
        这里保存了你与阿德勒式自我探索 Skill 的所有完整对话原文（逐字保存，未经改写）。<br>
        每段对话默认折叠，点击标题即可展开查看完整内容。对话按时间正序排列（最早在最上方，最新在最下方）。<br>
        生成时间：{now_str}
    </p>

    <div class="controls">
        <button onclick="expandAll()">📂 全部展开</button>
        <button onclick="collapseAll()">📁 全部收起</button>
    </div>

    <h2>对话目录（共 {len(conversations)} 段）</h2>
    <div class="toc">
        <ol>
{''.join(toc_items)}
        </ol>
    </div>

    <h2>对话内容</h2>
{''.join(conversation_blocks)}

    <div class="footer">
        本档案由阿德勒式自我探索 Skill 自动生成。所有对话均为逐字原文保存，未经改写。<br>
        你可以随时查看或删除任何对话记录。
    </div>

    <script>
        function toggleConversation(header) {{
            var conv = header.parentElement;
            conv.classList.toggle('open');
        }}
        function expandAll() {{
            document.querySelectorAll('.conversation').forEach(function(c) {{
                c.classList.add('open');
            }});
        }}
        function collapseAll() {{
            document.querySelectorAll('.conversation').forEach(function(c) {{
                c.classList.remove('open');
            }});
        }}
        function expandById(id) {{
            var conv = document.getElementById(id);
            if (conv) {{
                conv.classList.add('open');
            }}
        }}
    </script>
</body>
</html>'''

    return html_content


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="导出完整对话档案为交互式 HTML 文件")
    args = parser.parse_args()

    # 密码只从环境变量读取；不提供 --password 命令行参数（杜绝明文传密）
    password = os.environ.get("ADLERIAN_PASSWORD")

    project_root = Path(__file__).resolve().parents[1]
    auth_path = project_root / "storage" / "data" / "default" / "auth.json"
    conversations_dir = project_root / "storage" / "data" / "default" / "conversations"
    output_dir = project_root / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("导出完整对话档案为交互式 HTML")
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
            print("  $env:ADLERIAN_PASSWORD=\"<密码>\"; python scripts/export_archive_to_html.py")
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

    # 读取对话记录
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

    # 生成 HTML
    print("正在生成交互式 HTML 档案...")
    html_content = generate_html(conversations)

    # 固定文件名，每次查看覆盖上一次，outputs/ 目录不会积累大量历史文件
    output_filename = "我的对话档案.html"
    output_path = output_dir / output_filename

    # 原子写：先写临时文件并 fsync，再 os.replace，避免中断留下半份档案
    tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(html_content)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, output_path)

    print(f"  HTML 档案已保存：{output_path}")
    print()

    print("=" * 60)
    print("导出完成")
    print("=" * 60)
    print(f"  对话段数：{len(conversations)}")
    print(f"  输出文件：{output_path}")
    print()
    print("请在浏览器中打开此 HTML 文件查看交互式对话档案。")
    print("每段对话默认折叠，点击标题即可展开/收起。")
    print()


if __name__ == "__main__":
    main()
