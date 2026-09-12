"""
完整对话记录保存脚本

将一次完整对话（用户消息 + Skill 回复的逐字原文）保存到本地存储。
支持未加密存储和加密存储，支持超长对话分段追加。

【最高要求】完整对话记录只能来自"平台会话历史读取工具拉取的真实原文"，
严禁凭模型记忆/画像摘要重构（那必然概括，甚至编造出用户没说过的话）。
脚本内置五道硬校验，任何一道不过都拒绝写入：
  校验1【角色对等】user 与 assistant 消息数量必须基本对等（差值不超过 2）。
  校验2【交替性】不允许连续 3 条及以上同一角色。
  校验3【反提纲】不允许超过半数用户消息都是"短标签：内容"的提纲格式。
  校验4【真实时间戳】每条消息必须带会话历史里的真实 created_at（脚本不再自动补当前时间）；
      时间戳必须可解析、按时间单调不减；多条消息时间戳全部相同、或长对话时间跨度异常短，
      判定为"批量伪造时间戳"（凭记忆重构的典型铁证），拒绝。
  校验5【来源凭证】输入必须声明 transcript_source.method == "conversation_history"，
      即这些 messages 确系来自会话历史读取工具；凭记忆/画像重构（model_recall 等）一律拒绝。
  messages 必须按时间顺序，content 必须是工具返回的当时原话，严禁概括、改写、合并、提炼、脑补。

安全说明：
  密码通过环境变量 ADLERIAN_PASSWORD 传递，严禁在命令行参数中明文传递密码。

使用方式：
  # 未加密存储（一次性保存完整对话）
  python scripts/save_conversation.py --input <对话JSON文件路径>

  # 加密存储（通过环境变量传递密码）
  $env:ADLERIAN_PASSWORD="<密码>"; python scripts/save_conversation.py --input <对话JSON文件路径> --storage-mode local_encrypted

  # 超长对话分段追加：先创建（首段），再逐段追加
  python scripts/save_conversation.py --input <首段JSON>            # 输出 conv_id
  python scripts/save_conversation.py --input <次段JSON> --append-to <conv_id>

参数说明：
  --input: 对话数据的 JSON 文件路径（必需）
  --storage-mode: local_unencrypted（默认）或 local_encrypted
  --append-to: 已有对话记录 ID，提供时把 messages 追加到该记录（用于分段写入）

环境变量：
  ADLERIAN_PASSWORD: 加密存储的密码（仅当使用加密存储时需要）

输入的对话 JSON 格式（首次创建）：
{
  "summary": "本次对话的一句话摘要",
  "conversation_type": "initial_profile_building",
  "transcript_source": {                       // 【必需】来源凭证
    "method": "conversation_history",          //  必须是 conversation_history（会话历史工具拉取）
    "conversation_id": "来源会话ID，拿不到可留空字符串",
    "pulled_at": "拉取时间，可不填由脚本补",
    "turns": 21                                 //  拉取的轮次，可选
  },
  "messages": [
    {"role": "user", "content": "用户当时发的原话", "timestamp": "该消息真实created_at"},
    {"role": "assistant", "content": "Skill当时回复的原话", "timestamp": "该消息真实created_at"}
  ],
  "related_insights": [],
  "related_patterns": []
}
注意：messages 中每条都必须带 timestamp（来自会话历史工具的真实 created_at），脚本不再自动补当前时间。
分段追加时，JSON 需含 {"messages": [...]}（每条同样带真实 timestamp），来源继承首段。
"""

import sys
import os
import re
import json
import argparse
from datetime import datetime, timedelta
from pathlib import Path

# 基于脚本自身位置确定项目根目录（绝对路径，不依赖运行时工作目录）
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from storage.adapters.local_json import LocalJsonStorageAdapter
from storage.adapters.local_encrypted import LocalEncryptedStorageAdapter

# 固定的数据存储目录（绝对路径）
DATA_DIR = str(PROJECT_ROOT / "storage" / "data")
USER_ID = "default"

# 角色数量允许的最大差值（允许用户末尾补充一两条）
MAX_ROLE_DIFF = 2
# 允许连续同角色的最大条数（连续3条即判定为堆叠归纳）
MAX_SAME_ROLE_RUN = 2
# 反提纲：短标签+冒号的正则（2-6个中文/英文字词后接中/英文冒号）
OUTLINE_LABEL_RE = re.compile(r"^[\u4e00-\u9fa5A-Za-z0-9]{2,6}\s*[：:]")


# 时间戳真实性：达到该条数后若所有时间戳完全相同，判定批量伪造
SAME_TS_MIN_N = 4
# 时间戳真实性：达到该条数后若整体跨度短于该秒数，判定批量补时间戳
SPAN_MIN_N = 8
SPAN_MIN_SECONDS = 10
# 唯一合法的完整对话来源
VALID_SOURCE_METHOD = "conversation_history"
# 明确视为"凭记忆/画像重构"的非法来源
FORBIDDEN_SOURCE_METHODS = {
    "model_recall", "memory", "memory_reconstruct", "from_profile",
    "reconstructed", "manual_recall", "generated",
}


def parse_ts(value):
    """把 ISO 风格时间字符串解析为 naive datetime（仅用于比较顺序与跨度）。无法解析抛 ValueError。"""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("时间戳为空")
    s = value.strip().replace("Z", "+00:00")
    if "T" not in s:
        return datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is not None:
        dt = dt.replace(tzinfo=None)  # 统一去时区，只做相对比较
    return dt


def validate_source(data):
    """校验5【来源凭证】：完整对话必须来自会话历史读取工具，禁止凭记忆/画像重构。
    返回 (错误列表, 规范化来源dict)。"""
    errors = []
    src = data.get("transcript_source")
    if not isinstance(src, dict):
        errors.append(
            "缺少 transcript_source 来源凭证。完整对话必须来自平台会话历史读取工具，"
            "请在输入 JSON 中加入 transcript_source（method 必须为 conversation_history）；"
            "严禁凭模型记忆或画像摘要重构对话。"
        )
        return errors, None
    method = src.get("method")
    if method in FORBIDDEN_SOURCE_METHODS:
        errors.append(
            f"transcript_source.method=\"{method}\" 属于凭记忆/画像重构来源，禁止落盘。"
            f"必须改用会话历史读取工具拉取真实原文（method=conversation_history）。"
        )
    if method != VALID_SOURCE_METHOD:
        errors.append(
            f"transcript_source.method 必须是 \"{VALID_SOURCE_METHOD}\"（会话历史工具拉取），"
            f"当前为 \"{method}\"。拉不到真实历史时应如实告知用户只保存摘要，绝不允许编造。"
        )
    if errors:
        return errors, None
    normalized = {
        "method": VALID_SOURCE_METHOD,
        "conversation_id": str(src.get("conversation_id", "") or ""),
        "pulled_at": src.get("pulled_at") or datetime.now().isoformat(),
        "turns": src.get("turns"),
    }
    return errors, normalized


def validate_timestamps(messages):
    """校验4【真实时间戳】：每条必须带可解析的真实 created_at、单调不减；
    全部相同或长对话跨度异常短，判定为批量伪造。"""
    errors = []
    n = len(messages)
    parsed = []
    for i, m in enumerate(messages):
        ts = m.get("timestamp")
        if ts is None or (isinstance(ts, str) and not ts.strip()):
            errors.append(f"第 {i+1} 条消息缺少真实 timestamp（必须用会话历史里的 created_at，脚本不再自动补当前时间）")
            continue
        try:
            parsed.append(parse_ts(ts))
        except Exception:
            errors.append(f"第 {i+1} 条消息的 timestamp 无法解析：{ts!r}（应为会话历史返回的时间）")
    if errors or len(parsed) < 2:
        return errors

    for i in range(1, len(parsed)):
        if parsed[i] < parsed[i - 1]:
            errors.append(f"第 {i+1} 条消息时间戳早于前一条（消息未按时间排序），请按会话历史的真实顺序排列")
            break

    unique_ts = set(m.get("timestamp") for m in messages)
    if n >= SAME_TS_MIN_N and len(unique_ts) == 1:
        errors.append(
            f"{n} 条消息的时间戳完全相同——这是脚本批量补当前时间/凭记忆重构的铁证。"
            f"必须为每条消息填入会话历史返回的真实 created_at。"
        )
    if n >= SPAN_MIN_N:
        span = max(parsed) - min(parsed)
        if span < timedelta(seconds=SPAN_MIN_SECONDS):
            errors.append(
                f"{n} 条消息的真实时间跨度仅 {span.total_seconds():.1f} 秒，短到不合常理"
                f"（一问一答的多轮对话必然跨越更长时间），时间戳疑似批量伪造，请改用每条消息的真实 created_at。"
            )
    return errors


def validate_transcript(messages):
    """
    对完整消息序列做形式硬校验（角色对等/交替性/反提纲/真实时间戳）。
    来源凭证由 validate_source 单独校验。任何一条不通过都拒绝写入。
    """
    errors = []

    # 基础校验
    for i, msg in enumerate(messages):
        if "role" not in msg or "content" not in msg:
            errors.append(f"第 {i+1} 条消息缺少 role 或 content 字段")
            continue
        if msg["role"] not in ("user", "assistant"):
            errors.append(f"第 {i+1} 条消息的 role 非法：{msg['role']}（只允许 user/assistant）")
        if not isinstance(msg.get("content"), str) or not msg["content"].strip():
            errors.append(f"第 {i+1} 条消息内容为空（逐字原文不能是空消息或摘要占位）")
    if errors:
        return errors

    user_idx = [i for i, m in enumerate(messages) if m["role"] == "user"]
    asst_idx = [i for i, m in enumerate(messages) if m["role"] == "assistant"]
    user_n, asst_n = len(user_idx), len(asst_idx)

    # 校验1：角色对等
    if user_n == 0:
        errors.append("没有任何用户消息，不可能是完整对话记录")
    if asst_n == 0:
        errors.append("没有任何 Skill 回复消息——你很可能只保存了用户发言的归纳，"
                      "完整对话必须包含 Skill 每一轮的回复原文")
    if asst_n < user_n - MAX_ROLE_DIFF:
        errors.append(
            f"角色严重不对等：用户消息 {user_n} 条、Skill 回复仅 {asst_n} 条（差 {user_n - asst_n} 条）。"
            f"真实对话一来一回，数量应基本相等。这说明你把多轮对话压缩成了用户要点归纳、"
            f"丢失了 Skill 的回复。请回到对话，按真实轮次逐字重建 user/assistant 交替的 messages，"
            f"不要合并、不要概括。"
        )

    # 校验2：交替性（不允许连续超过 MAX_SAME_ROLE_RUN 条同角色）
    run_role, run_len = messages[0]["role"], 1
    for m in messages[1:]:
        if m["role"] == run_role:
            run_len += 1
            if run_len > MAX_SAME_ROLE_RUN:
                errors.append(
                    f"存在连续 {run_len} 条 {run_role} 消息——你很可能把多轮同角色内容堆叠/合并了。"
                    f"真实对话按时间交替推进，请把被合并的轮次拆开，并补回中间另一方的原话。"
                )
                break
        else:
            run_role, run_len = m["role"], 1

    # 校验3：反提纲（用户消息大量是"短标签：内容"格式）
    if user_n >= 4:
        outline_hits = sum(
            1 for i in user_idx
            if OUTLINE_LABEL_RE.match(messages[i]["content"].strip())
        )
        if outline_hits > user_n / 2:
            examples = [messages[i]["content"].strip()[:14]
                        for i in user_idx if OUTLINE_LABEL_RE.match(messages[i]["content"].strip())][:3]
            errors.append(
                f"检测到提纲式归纳：{user_n} 条用户消息中有 {outline_hits} 条以"
                f"\"短标签：\"开头（例如 {examples}）。这是把用户多轮原话改写成分类要点的特征，"
                f"不是逐字原文。请改用用户当时实际发送的整段原话，不要用\"家庭：…\"\"早期记忆：…\"这类归纳标签。"
            )

    # 校验4：真实时间戳（必须来自会话历史，禁止批量补当前时间）
    errors.extend(validate_timestamps(messages))

    return errors


def load_messages(input_path):
    """读取输入 JSON，返回 (data, messages)"""
    try:
        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"错误：输入文件不是有效的 JSON: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"错误：读取输入文件失败: {e}")
        sys.exit(1)

    messages = data.get("messages", [])
    if not isinstance(messages, list) or not messages:
        print("错误：输入 JSON 缺少非空的 messages 字段（逐字原文消息列表）")
        sys.exit(1)
    # 注意：不再为缺失 timestamp 的消息自动补当前时间——那会掩盖"凭记忆重构"。
    # 每条消息必须带会话历史返回的真实 created_at，由 validate_timestamps 强制校验。
    return data, messages


def get_storage(storage_mode, password):
    """初始化存储适配器（始终使用绝对路径）"""
    if storage_mode == "local_encrypted":
        if not password:
            print("错误：使用加密存储时必须通过环境变量 ADLERIAN_PASSWORD 提供密码")
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


def create_conversation(data, messages, storage, source):
    """首次创建对话记录（source 为已校验的来源凭证）"""
    # 创建时对整段做完整校验（含真实时间戳）
    errors = validate_transcript(messages)
    if errors:
        print("❌ 完整对话记录校验未通过，已拒绝保存。请修正后重试：")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)

    now = datetime.now().isoformat()
    entry = {
        "summary": data.get("summary", "（无摘要）"),
        "conversation_type": data.get("conversation_type", "exploration"),
        "related_insights": data.get("related_insights", []),
        "related_patterns": data.get("related_patterns", []),
        "user_confirmed": data.get("user_confirmed", True),
        "full_transcript": {
            "enabled": True,
            "messages": messages,
            "message_count": len(messages),
            "saved_at": now,
            # 来源凭证：证明这些 messages 来自会话历史工具，而非模型重构
            "source": source["method"],
            "source_conversation_id": source.get("conversation_id", ""),
            "pulled_at": source.get("pulled_at", now),
            "source_turns": source.get("turns"),
        },
    }
    conv_id = storage.append_conversation(entry)

    saved = storage.get_conversation(conv_id)
    if not saved:
        print("错误：保存后无法读回对话记录")
        sys.exit(1)
    saved_count = saved.get("full_transcript", {}).get("message_count", 0)
    if saved_count != len(messages):
        print(f"错误：保存后条数不一致（传入 {len(messages)}，读回 {saved_count}）")
        sys.exit(1)
    return conv_id, saved


def append_to_conversation(conv_id, new_messages, storage):
    """向已有对话分段追加，并对【合并后的完整序列】重新做整体校验"""
    existing = storage.get_conversation(conv_id)
    if existing is None:
        print(f"错误：要追加的对话记录不存在：{conv_id}")
        sys.exit(1)
    existing_msgs = existing.get("full_transcript", {}).get("messages", [])
    combined = existing_msgs + new_messages

    errors = validate_transcript(combined)
    if errors:
        print("❌ 追加后完整对话校验未通过，已拒绝追加。请修正本段后重试：")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)

    stats = storage.append_conversation_messages(conv_id, new_messages)
    return conv_id, stats


def main():
    parser = argparse.ArgumentParser(description="保存完整对话记录（逐字原文，内置反摘要硬校验）")
    parser.add_argument("--input", required=True, help="对话数据 JSON 文件路径")
    parser.add_argument("--storage-mode", default="local_unencrypted",
                        choices=["local_unencrypted", "local_encrypted"],
                        help="存储模式（默认 local_unencrypted）")
    parser.add_argument("--append-to", default=None,
                        help="已有对话记录 ID；提供时把 messages 分段追加到该记录")
    args = parser.parse_args()

    password = os.environ.get("ADLERIAN_PASSWORD")
    if args.storage_mode == "local_encrypted" and not password:
        print("错误：使用加密存储时必须通过环境变量 ADLERIAN_PASSWORD 提供密码")
        print("安全提示：严禁在命令行参数中明文传递密码，应使用环境变量传递")
        sys.exit(1)

    data, messages = load_messages(args.input)
    storage = get_storage(args.storage_mode, password)

    if args.append_to:
        # 分段追加：来源继承首段，新消息的真实时间戳由合并后整体校验把关
        conv_id, stats = append_to_conversation(args.append_to, messages, storage)
        print("=" * 60)
        print("完整对话记录分段追加成功")
        print("=" * 60)
        print(f"对话记录 ID: {conv_id}")
        print(f"本段新增: {len(messages)} 条；累计消息: {stats['message_count']} 条")
        print(f"  - 累计用户消息: {stats['user_count']} 条")
        print(f"  - 累计Skill回复: {stats['assistant_count']} 条")
        print("=" * 60)
    else:
        # 首次创建：先校验来源凭证（必须来自会话历史，禁止凭记忆重构）
        src_errors, source = validate_source(data)
        if src_errors:
            print("❌ 完整对话来源校验未通过，已拒绝保存：")
            for e in src_errors:
                print(f"  - {e}")
            sys.exit(1)
        conv_id, saved = create_conversation(data, messages, storage, source)
        user_n = sum(1 for m in messages if m["role"] == "user")
        asst_n = sum(1 for m in messages if m["role"] == "assistant")
        print("=" * 60)
        print("✅ 完整对话记录保存成功（来源=会话历史原文，已通过五道硬校验）")
        print("=" * 60)
        print(f"对话记录 ID: {conv_id}")
        print(f"对话类型: {saved.get('conversation_type')}")
        print(f"消息总条数: {saved.get('full_transcript', {}).get('message_count')}")
        print(f"  - 用户消息: {user_n} 条")
        print(f"  - Skill回复: {asst_n} 条")
        print(f"摘要: {saved.get('summary', '')[:80]}")
        print("=" * 60)


if __name__ == "__main__":
    main()
