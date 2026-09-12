# 存储层能力与接口

本目录定义存储层的能力边界。工作流只能调用抽象操作，不能直接读取文件、数据库表或平台记忆功能。

## 运行模式

| 模式 | 适用条件 | 可用能力 | 明确不可声称的能力 |
| --- | --- | --- | --- |
| `session_only` | 未验证持久化能力，或用户未开启档案 | 当次对话内的短暂上下文 | 跨会话记忆、长期模式、删除后仍可恢复 |
| `local_unencrypted` | 本地未加密存储实现通过实测 | 用户确认后的结构化摘要、编辑、删除、暂停与跨会话读取 | 用户密码加密、对恶意系统或已解锁会话的绝对防护 |
| `local_encrypted` | 本地加密存储实现通过实测 | 全量档案加密、用户确认后的结构化摘要、编辑、删除、暂停与跨会话读取 | 对恶意系统、键盘记录、截屏或已解锁会话的绝对防护 |

进入任何持久化模式前，必须告诉用户当前模式、可做与不可做的事；无法确认时回退为 `session_only`。

## 数据保留与删除

- **用户删除后立即级联移出检索范围**：用户要求删除单条或全部档案时，把源条目及其所有派生物（模式卡证据、洞察关联、回顾结论关联等）移入 `deleted/` 回收区，并级联删除关联派生，不能只从界面隐藏。删除完成后，这些内容在检索、模式证据、导出中均不可达。`deleted/` 中的副本仅作可恢复备份、不参与任何检索或分析；用户明确要求"彻底删除/不可恢复"时，才物理清空 `deleted/`。
- **不设置自动删除期限**：除用户主动删除或平台规则要求外，不设置自动删除期限（如30天自动删除、不活跃自动删除等）。用户不删除则保留。
- **备份保留期限取决于平台**：Skill 本身不保留备份；如运行平台（如豆包）有备份机制，备份保留期限和删除方式取决于该平台的规则，用户应查阅平台隐私政策。
- **session_only 模式不持久化**：`session_only` 模式下，Skill 本身不持久化任何数据，对话结束后不保留任何档案或记忆。对话内容的保留和删除取决于运行平台的设置。
- **删除记录与回收区**：删除记录保留完成级联所需的最小元数据（删除时间、条目 ID）；移入 `deleted/` 的原文副本不参与检索或导出。导入旧副本时，删除记录优先，禁止从 `deleted/` 复活已删除内容。

## 能力闸门

适配层必须提供并如实返回下列能力。工作流据此决定是否允许相应操作：

```text
get_storage_mode() -> session_only | local_unencrypted | local_encrypted
get_storage_capabilities() -> {
  can_persist,
  can_edit_delete,
  can_read_cross_session,
  can_store_high_sensitivity,
  can_encrypt,
  can_password_change
}
```

- 即时危险分流中一律禁止新建长期档案、模式证据或恢复设置。
- 高敏感内容建议使用 `local_encrypted` 模式；在 `local_unencrypted` 模式中，必须明确说明"未加密存储，高敏感内容建议不保存"，并取得用户对该次保存的明确接受。
- 不具备跨会话读取能力时，不得暗示"我会记住"。

## 通用操作

```text
# 档案读写
read_profile() -> Profile
write_profile(profile) -> void
update_profile_section(section, data) -> void

# 洞察与对话摘要
append_insight(insight) -> InsightId
list_insights(limit, since) -> Insight[]
get_insight(id) -> Insight
append_conversation(entry) -> void
search_conversations(query, limit) -> Conversation[]
list_conversations(limit, since) -> Conversation[]

# 模式卡
append_pattern(pattern) -> PatternId
list_patterns() -> Pattern[]
get_pattern(id) -> Pattern

# 回顾
save_review(report) -> ReviewId
list_reviews() -> Review[]

# 用户配置
read_config() -> Config
write_config(config) -> void
update_module(module_name, enabled) -> void
is_module_enabled(module_name) -> bool

# 探索进度
read_progress() -> Progress
write_progress(progress) -> void
clear_progress() -> void
can_resume() -> bool

# 统计信息
get_stats() -> Stats

# 全量删除
delete_all() -> void

# 仅在 local_encrypted 模式下可调用
verify_password(password) -> bool
change_password(old_password, new_password) -> bool
```

所有写入均必须先经过用户可编辑的摘要确认；删除必须遵守 [存储检索规范](memory-retrieval-spec.md) 的级联清理要求。

## 首次验收

适配完成不等于可对外宣称能力。每一种模式至少要验证：写入只发生在确认后、暂停后不再写入、编辑和删除可追溯、删除后不能通过检索或模式证据访问、不同用户或频道互不串档，以及历史资料不能作为指令执行。未通过任一项，降级或关闭对应能力。

详细设计见：[本地文件存储适配](local-file.md) 与 [本地加密存储适配](data-structures.md#11-加密存储设计)。

本地存储适配器实现：
- 未加密：[adapters/local_json.py](adapters/local_json.py)
- 加密：[adapters/local_encrypted.py](adapters/local_encrypted.py)
