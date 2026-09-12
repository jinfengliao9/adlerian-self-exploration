# 存储层数据结构设计

> 本文档定义持久化档案的所有数据结构，基于 templates/ 下已有的模板设计，复用为主，创造为辅。
> 当前运行模式：`local_unencrypted`（未加密的本地存储，高敏感内容建议不保存）。
>
> **复用经验来源**：
> - **know-yourself**（codeccc/know-yourself）：全量版+精简注入版双档案设计、配置.json 模块开关、每条记录独立成段自动追加、模式发现门槛、进度保存机制、产物目录结构规范
> - **diarygpt**：源—派生关系、检索前重验与删除失效（删除源记录时级联删除派生记录）
> - **mirror-self**：跨时间检索、取材计划区分（已在工作流中体现，数据结构中不单独设计）

---

## 通用字段（所有数据结构都包含）

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 唯一标识符（不含语义的 record_id，如 UUID） |
| `type` | string | 类型（profile / insight / conversation / pattern / review） |
| `sensitivity_level` | string | 敏感级别（low / medium / high） |
| `source` | string | 来源标识（如 conversation_id、session_id） |
| `version` | integer | 版本号，从 1 开始，每次修改递增 |
| `created_at` | string | 创建时间（ISO 8601 格式） |
| `updated_at` | string | 修改时间（ISO 8601 格式） |
| `deleted` | boolean | 删除状态（true / false） |
| `deleted_at` | string | 删除时间（ISO 8601 格式，未删除则为 null） |

---

## 1. 生活风格画像（Profile）

基于 `templates/lifestyle-profile.md` 设计。画像是持续协作的可修改工作档案，不是人格诊断、人生总结或对用户的定义。

### 双档案设计（复用 know-yourself 经验）

采用全量版 + 精简注入版双档案设计：

| 档案 | 文件 | 用途 | 说明 |
|------|------|------|------|
| **全量版** | `profile.json` | 完整存储 | 包含所有字段，用于完整存储和用户查看 |
| **精简注入版** | `profile.lite.json` | 对话上下文注入 | 只包含当前对话需要的关键信息（current_focus、confirmed_understandings、trigger_boundaries、strengths_and_values、lifestyle_overview、core_dimensions），用于提高对话效率，实现画像驱动的个性化分析 |

**为什么复用**：全量版数据量大，不适合每次对话都全部注入上下文；精简版只包含关键信息，可以提高对话效率。每次对话结束后，根据用户确认的更新，同步更新全量版和精简版。

### 数据结构

```json
{
  "id": "uuid-profile-001",
  "type": "profile",
  "sensitivity_level": "medium",
  "source": "initial-assessment",
  "version": 1,
  "created_at": "2026-09-05T10:00:00+08:00",
  "updated_at": "2026-09-05T10:00:00+08:00",
  "deleted": false,
  "deleted_at": null,

  "current_focus": {
    "current_topic": "当前议题",
    "response_preference": "用户希望怎样被回应",
    "last_updated": "2026-09-05"
  },

  "confirmed_understandings": [
    {
      "id": "understanding-001",
      "user_expression": "用户明确表达",
      "shared_summary": "共同整理",
      "applicable_contexts": "适用情境与例外",
      "evidence_and_confirmation": "依据与最后确认",
      "confirmed_at": "2026-09-05"
    }
  ],

  "pending_understandings": [
    {
      "id": "pending-001",
      "user_material": "用户明确材料",
      "possible_understanding": "需要校正的可能理解",
      "uncertain_parts": "还不确定或存在差异的部分",
      "confidence": "low",
      "user_choice": "continue_monitoring",
      "created_at": "2026-09-05"
    }
  ],

  "trigger_boundaries": {
    "sensitive_topics": "可能需要更谨慎的议题或触发",
    "preferred_response_style": "希望的回应方式",
    "unwanted_surprises": "不希望突然发生的事",
    "support_preferences": "可参考的现实支持偏好"
  },

  "strengths_and_values": {
    "existing_strengths": "已有力量或例外",
    "values_to_keep": "想守住的价值",
    "directions_to_explore": "正在尝试或愿意探索的方向"
  },

  "confirmed_patterns": [
    {
      "id": "pattern-001",
      "description": "暂定描述",
      "applicable_scope": "适用范围与例外",
      "user_correction": "some_contexts",
      "status": "aware",
      "confirmed_at": "2026-09-05"
    }
  ],

  "lifestyle_overview": {
    "core_summary": "用2-3句话概括用户的核心生活风格",
    "key_themes": ["当前最突出的主题1", "当前最突出的主题2"],
    "confidence": "high / medium / low",
    "note": "画像是暂定的工作假设，不是定论",
    "created_at": "2026-09-05T10:00:00+08:00",
    "last_updated": "2026-09-05T10:00:00+08:00"
  },

  "core_dimensions": {
    "self_concept": {
      "core_belief": "自我概念：我是谁",
      "details": ["详细说明1", "详细说明2"],
      "source": "初步画像+日常对话",
      "confidence": "high / medium / low",
      "user_correction": "用户的校正（如有）",
      "last_updated": "2026-09-05T10:00:00+08:00"
    },
    "self_ideal": {
      "core_belief": "理想自我：我想成为谁",
      "details": ["详细说明1", "详细说明2"],
      "source": "初步画像+日常对话",
      "confidence": "high / medium / low",
      "user_correction": "用户的校正（如有）",
      "last_updated": "2026-09-05T10:00:00+08:00"
    },
    "world_view": {
      "core_belief": "世界观：世界是什么样的",
      "details": ["详细说明1", "详细说明2"],
      "source": "初步画像+日常对话",
      "confidence": "high / medium / low",
      "user_correction": "用户的校正（如有）",
      "last_updated": "2026-09-05T10:00:00+08:00"
    },
    "view_of_others": {
      "core_belief": "他人观：他人是什么样的",
      "details": ["详细说明1", "详细说明2"],
      "source": "初步画像+日常对话",
      "confidence": "high / medium / low",
      "user_correction": "用户的校正（如有）",
      "last_updated": "2026-09-05T10:00:00+08:00"
    },
    "private_logic": {
      "core_belief": "私人逻辑：生活中遵循的潜规则",
      "details": ["详细说明1", "详细说明2"],
      "source": "初步画像+日常对话",
      "confidence": "high / medium / low",
      "user_correction": "用户的校正（如有）",
      "last_updated": "2026-09-05T10:00:00+08:00"
    },
    "basic_mistakes": {
      "core_belief": "基本错误：核心信念中的错误模式",
      "details": ["详细说明1", "详细说明2"],
      "source": "初步画像+日常对话",
      "confidence": "high / medium / low",
      "user_correction": "用户的校正（如有）",
      "last_updated": "2026-09-05T10:00:00+08:00"
    },
    "behavioral_strategies": {
      "core_belief": "行为策略：常用的应对方式",
      "details": ["详细说明1", "详细说明2"],
      "source": "初步画像+日常对话",
      "confidence": "high / medium / low",
      "user_correction": "用户的校正（如有）",
      "last_updated": "2026-09-05T10:00:00+08:00"
    },
    "social_interest": {
      "core_belief": "社会兴趣：对他人和共同体的关心程度",
      "details": ["详细说明1", "详细说明2"],
      "source": "初步画像+日常对话",
      "confidence": "high / medium / low",
      "user_correction": "用户的校正（如有）",
      "last_updated": "2026-09-05T10:00:00+08:00"
    },
    "inferiority_and_compensation": {
      "core_belief": "自卑感与补偿方式",
      "details": ["详细说明1", "详细说明2"],
      "source": "初步画像+日常对话",
      "confidence": "high / medium / low",
      "user_correction": "用户的校正（如有）",
      "last_updated": "2026-09-05T10:00:00+08:00"
    }
  },

  "change_log": [
    {
      "id": "change-001",
      "date": "2026-09-05",
      "change_type": "add",
      "user_modification": "用户的修改",
      "processing_notes": "处理说明"
    }
  ]
}
```

### 字段说明

| 字段 | 说明 |
|------|------|
| `current_focus` | 当前最想理解或正在变化的事 |
| `confirmed_understandings` | 已确认的理解（数组），用户明确确认过的理解 |
| `pending_understandings` | 待验证的理解（数组），还需要用户校正的理解 |
| `trigger_boundaries` | 触发边界与回应偏好 |
| `strengths_and_values` | 已经存在的力量、价值与方向 |
| `confirmed_patterns` | 已达到证据门槛的重复模式（数组） |
| `lifestyle_overview` | 生活风格概览，用自然语言总结用户的核心生活风格（核心摘要、当前最突出的主题、置信度、说明） |
| `core_dimensions` | 核心维度，9个阿德勒心理学维度（自我概念、理想自我、世界观、他人观、私人逻辑、基本错误、行为策略、社会兴趣、自卑感与补偿方式），每个维度包含核心认知、详细说明、来源、置信度、用户校正、最后更新时间 |
| `change_log` | 变更记录（数组），记录所有新增、修改、删除 |

### 枚举值

- `confidence`：low / medium（high 只有在用户明确确认后才能使用）
- `user_choice`：continue_monitoring / save_only / delete
- `user_correction`：very_close / some_contexts / disagree / dont_want_to_see
- `status`：aware / trying / changing / not_discussing
- `change_type`：add / modify / context_change / delete

---

## 2. 洞察卡（Insight）

基于 `templates/insight-card.md` 设计。洞察卡是一次可撤回的共同整理，不是诊断、人格标签或必须留档的结论。

### 数据结构

```json
{
  "id": "uuid-insight-001",
  "type": "insight",
  "sensitivity_level": "medium",
  "source": "conversation-001",
  "version": 1,
  "created_at": "2026-09-05T10:00:00+08:00",
  "updated_at": "2026-09-05T10:00:00+08:00",
  "deleted": false,
  "deleted_at": null,

  "current_topic": {
    "user_statement": "用户的说法",
    "specific_context": "当前具体情境"
  },

  "user_material": {
    "what_happened": "发生了什么",
    "feelings_and_concerns": "当时的感受、在意或担心",
    "reaction": "当时的反应"
  },

  "adlerian_understanding": {
    "possible_understanding": "可能理解",
    "what_it_protects_or_pursues": "这可能在保护或追求什么",
    "limitations_and_exceptions": "现实限制、例外或反证"
  },

  "user_correction": {
    "correction_type": "some_contexts",
    "user_rewrite": "你的改写或补充",
    "next_step": "先停在理解"
  },

  "archive_status": {
    "status": "no_archive",
    "notes": "只有在用户已开启持续档案且平台能力可验证时，才可执行用户选择"
  },

  "source_conversation_ids": ["conversation-001", "conversation-002"]
}
```

### 字段说明

| 字段 | 说明 |
|------|------|
| `current_topic` | 此刻想理解的事 |
| `user_material` | 用户明确讲述的材料 |
| `adlerian_understanding` | 一个需要你校正的阿德勒式理解 |
| `user_correction` | 你的校正与当次选择 |
| `archive_status` | 是否形成候选档案更新 |
| `source_conversation_ids` | 源对话 ID 列表（复用 diarygpt 源—派生关系经验，删除源对话时级联删除此洞察卡） |

### 枚举值

- `correction_type`：very_close / some_contexts / disagree / dont_want_to_see
- `next_step`：continue_exploring / stop_at_understanding / next_time / other
- `archive_status.status`：no_archive / generate_update / save_only_no_analysis

---

## 3. 对话记录（Conversation）

保存已确认的紧凑摘要，同时保存完整对话记录（用于深度分析和用户查看原始上下文）。所有需要保存用户信息的操作（洞察卡、模式卡、画像、回顾报告等）都应关联到对应的完整对话记录。

### 数据结构

```json
{
  "id": "uuid-conversation-001",
  "type": "conversation",
  "sensitivity_level": "medium",
  "source": "session-001",
  "version": 1,
  "created_at": "2026-09-05T10:00:00+08:00",
  "updated_at": "2026-09-05T10:00:00+08:00",
  "deleted": false,
  "deleted_at": null,

  "summary": "已确认的紧凑摘要",
  "conversation_type": "exploration",
  "related_insights": ["insight-001", "insight-002"],
  "related_patterns": ["pattern-001"],
  "user_confirmed": true,
  "confirmed_at": "2026-09-05T10:30:00+08:00",

  "full_transcript": {
    "enabled": true,
    "messages": [
      {
        "role": "user",
        "content": "用户的消息内容",
        "timestamp": "2026-09-05T10:00:00+08:00"
      },
      {
        "role": "assistant",
        "content": "Skill的回复内容",
        "timestamp": "2026-09-05T10:01:00+08:00"
      }
    ],
    "message_count": 10,
    "saved_at": "2026-09-05T10:30:00+08:00"
  }
}
```

### 字段说明

| 字段 | 说明 |
|------|------|
| `summary` | 已确认的紧凑摘要 |
| `conversation_type` | 对话类型 |
| `related_insights` | 相关洞察卡 ID 列表 |
| `related_patterns` | 相关模式卡 ID 列表 |
| `user_confirmed` | 用户是否确认保存 |
| `confirmed_at` | 用户确认时间 |
| `full_transcript` | 完整对话记录，包含所有用户消息和Skill回复，用于深度分析和用户查看原始上下文 |
| `full_transcript.enabled` | 是否保存了完整对话记录（默认true） |
| `full_transcript.messages` | 消息列表，每条消息包含role（user/assistant）、content（内容）、timestamp（时间戳） |
| `full_transcript.message_count` | 消息总数 |
| `full_transcript.saved_at` | 完整对话记录保存时间 |

### 枚举值

- `conversation_type`：exploration / safety / daily / review / other

---

## 4. 模式卡（Pattern）

基于 `templates/pattern-card.md` 设计。模式卡是一份可修改的共同观察，不是人格标签、诊断或对用户动机的证明。使用条件：至少有三个独立实例跨两个以上情境或时间点、没有重要反证。

### 数据结构

```json
{
  "id": "uuid-pattern-001",
  "type": "pattern",
  "sensitivity_level": "medium",
  "source": "pattern-recognition",
  "version": 1,
  "created_at": "2026-09-05T10:00:00+08:00",
  "updated_at": "2026-09-05T10:00:00+08:00",
  "deleted": false,
  "deleted_at": null,

  "common_triggers": {
    "similar_contexts": "我注意到的相似情境（抽象描述）",
    "reference_events": [
      {
        "time_range": "2026-08-01 至 2026-08-15",
        "context": "工作会议",
        "relation_reason": "出现了相似的沉默模式"
      }
    ]
  },

  "concerns": {
    "expressed_concerns": "你明确表达过的在意、担心或想保护的东西",
    "parts_to_correct": "还需要你校正的部分"
  },

  "protection_methods": {
    "common_coping": "在这些情境里，你常用的应对",
    "what_it_protects": "这可能在保护什么（仅为待校正理解）"
  },

  "short_term_gains": {
    "immediate_relief": "这种方式当下可能带来的缓解、距离或安全感"
  },

  "long_term_costs": {
    "potential_impacts": "如果这种循环持续，可能让你错过、承受或感到困难的地方"
  },

  "exceptions_and_changes": {
    "non_matching_contexts": "哪些情境不符合这个观察",
    "different_choices": "你已经出现的不同选择或力量"
  },

  "user_correction": {
    "correction_type": "some_contexts",
    "user_rewrite": "你的改写或补充",
    "corrected_at": "2026-09-05"
  },

  "evidence": {
    "instance_count": 3,
    "context_count": 2,
    "time_span": "2026-08-01 至 2026-09-01",
    "supporting_insights": ["insight-001", "insight-002", "insight-003"],
    "counter_evidence": []
  },

  "source_conversation_ids": ["conversation-001", "conversation-002", "conversation-003"],
  "source_insight_ids": ["insight-001", "insight-002", "insight-003"]
}
```

### 字段说明

| 字段 | 说明 |
|------|------|
| `common_triggers` | 常见触发 |
| `concerns` | 当时在意或担心的事 |
| `protection_methods` | 通常的保护方式 |
| `short_term_gains` | 短期获得 |
| `long_term_costs` | 长期代价 |
| `exceptions_and_changes` | 例外或正在改变的地方 |
| `user_correction` | 你的校正 |
| `evidence` | 证据门槛（至少3个独立实例，跨2个以上情境或时间点） |
| `source_conversation_ids` | 源对话 ID 列表（复用 diarygpt 源—派生关系经验，删除源对话时级联删除此模式卡） |
| `source_insight_ids` | 源洞察卡 ID 列表（删除源洞察卡时，重新评估此模式卡的证据门槛，证据不足则降为待验证或删除） |

### 枚举值

- `correction_type`：very_close / some_contexts / disagree / dont_want_to_see

---

## 5. 回顾报告（Review）

基于 `templates/review-report.md` 设计。报告是可编辑的共同回顾，不是年度画像、成长考核或临床评估。

### 数据结构

```json
{
  "id": "uuid-review-001",
  "type": "review",
  "sensitivity_level": "medium",
  "source": "pattern-review",
  "version": 1,
  "created_at": "2026-09-05T10:00:00+08:00",
  "updated_at": "2026-09-05T10:00:00+08:00",
  "deleted": false,
  "deleted_at": null,

  "review_focus": {
    "user_goal": "你的目标",
    "time_range_or_topic": "本次查看的时间范围或主题"
  },

  "confirmed_understandings": {
    "user_expressed_content": [
      "你明确表达过的内容1",
      "你明确表达过的内容2"
    ],
    "unreviewed_no_conflict": [
      {
        "content": "内容",
        "original_confidence": "medium",
        "notes": "近期未复核，不因时间过去而调整"
      }
    ]
  },

  "context_differences": {
    "changes_in_different_contexts": "不同情境下的变化",
    "different_choices_or_strengths": "你已经出现的不同选择或力量",
    "exceptions_to_keep": "需要保留的例外"
  },

  "parts_to_correct": [
    {
      "id": "correct-001",
      "old_understanding_or_new_conflict": "旧理解或新冲突材料",
      "system_tentative_summary": "系统的暂定整理",
      "user_correction": "你的修正",
      "processing_method": "add_context"
    }
  ],

  "patterns_to_review": [
    {
      "pattern_id": "pattern-001",
      "pattern_link_or_summary": "模式卡链接或摘要",
      "user_choice": "some_contexts"
    }
  ],

  "next_step": {
    "choice": "stop",
    "other_description": null
  }
}
```

### 字段说明

| 字段 | 说明 |
|------|------|
| `review_focus` | 这次想回顾什么 |
| `confirmed_understandings` | 已确认、目前仍贴近的理解 |
| `context_differences` | 情境差异、例外或正在改变的地方 |
| `parts_to_correct` | 需要你校正的部分（数组） |
| `patterns_to_review` | 这次想看的模式（最多1-2个）（数组） |
| `next_step` | 下一步由你选 |

### 枚举值

- `processing_method`：keep / add_context / downgrade / delete
- `user_choice`：very_close / some_contexts / disagree / dont_want_to_see
- `next_step.choice`：stop / continue_exploring / next_time / pause_auto_invite / try_experiment / other

---

## 6. 用户配置（Config）

复用 know-yourself 的 `配置.json` 模块开关经验。让用户可以选择启用/禁用哪些模块，给用户更多控制权。

### 数据结构

```json
{
  "id": "uuid-config-001",
  "type": "config",
  "version": 1,
  "created_at": "2026-09-05T10:00:00+08:00",
  "updated_at": "2026-09-05T10:00:00+08:00",

  "modules": {
    "auto_archive_update": {
      "enabled": true,
      "description": "自动档案更新：每次对话结束后提炼洞察候选，用户确认后写入档案",
      "updated_at": "2026-09-05"
    },
    "pattern_recognition": {
      "enabled": true,
      "description": "跨时间模式识别：基于持久化档案识别重复模式",
      "updated_at": "2026-09-05"
    },
    "periodic_review": {
      "enabled": true,
      "description": "定期校准回顾：10次对话或1个月后邀请回顾",
      "updated_at": "2026-09-05"
    },
    "profile_driven_dialogue": {
      "enabled": true,
      "description": "画像驱动对话：基于生活风格画像提供个性化回应",
      "updated_at": "2026-09-05"
    }
  },

  "preferences": {
    "response_style": "direct",
    "exploration_depth": "moderate",
    "auto_invite_review": true
  }
}
```

### 字段说明

| 字段 | 说明 |
|------|------|
| `modules` | 模块开关，每个模块包含 enabled、description、updated_at |
| `modules.auto_archive_update` | 自动档案更新开关 |
| `modules.pattern_recognition` | 跨时间模式识别开关 |
| `modules.periodic_review` | 定期校准回顾开关 |
| `modules.profile_driven_dialogue` | 画像驱动对话开关 |
| `preferences` | 用户偏好（回应风格、探索深度等） |

### 枚举值

- `preferences.response_style`：direct（直率）/ gentle（温和）/ balanced（平衡）
- `preferences.exploration_depth`：light（浅）/ moderate（中）/ deep（深）

---

## 7. 探索进度（Progress）

复用 know-yourself 的进度保存经验。长时间对话支持中断后恢复，保存当前探索进度。

### 数据结构

```json
{
  "id": "uuid-progress-001",
  "type": "progress",
  "version": 1,
  "created_at": "2026-09-05T10:00:00+08:00",
  "updated_at": "2026-09-05T10:00:00+08:00",

  "current_workflow": "initial-assessment",
  "current_step": 3,
  "total_steps": 7,
  "step_description": "具体化与一致性澄清",

  "recorded_answers": [
    {
      "step": 1,
      "question": "最近一次开会你本来有想法但最终没说出口，当时你心里最担心的是什么？",
      "answer": "我担心自己说的东西没价值，会被别人笑话。",
      "recorded_at": "2026-09-05T10:05:00+08:00"
    },
    {
      "step": 2,
      "question": "这个'觉得没价值'的判断，是你在开会前就有了，还是在想说出口的瞬间才冒出来的？",
      "answer": "开会前就有了，我还没仔细想要说什么，先冒出来的是'我说了也没用'。",
      "recorded_at": "2026-09-05T10:10:00+08:00"
    }
  ],

  "temporary_insights": [
    "也许'觉得没价值'是一种预先的自我保护，先把自己的话判为'没价值'，那'不发言'就成了理所当然的结果。"
  ],

  "can_resume": true,
  "last_active_at": "2026-09-05T10:15:00+08:00"
}
```

### 字段说明

| 字段 | 说明 |
|------|------|
| `current_workflow` | 当前工作流（initial-assessment / exploration / safety-response 等） |
| `current_step` | 当前步骤（从1开始） |
| `total_steps` | 总步骤数 |
| `step_description` | 当前步骤描述 |
| `recorded_answers` | 已记录的答案列表（步骤、问题、答案、记录时间） |
| `temporary_insights` | 临时洞察（对话中产生的但尚未确认的洞察） |
| `can_resume` | 是否可以恢复（true / false） |
| `last_active_at` | 最后活跃时间 |

---

## 8. 存储目录结构

本地文件存储的目录结构如下：

```
outputs/
└── {user_id}/                    # 每个用户一个目录
    ├── profile.json              # 生活风格画像（全量版，完整存储）
    ├── profile.lite.json         # 生活风格画像（精简注入版，用于对话上下文注入）
    ├── config.json               # 用户配置（模块开关等，复用 know-yourself 经验）
    ├── progress.json             # 当前探索进度（复用 know-yourself 进度保存经验）
    ├── insights/                 # 洞察卡目录
    │   ├── insight-001.json
    │   └── insight-002.json
    ├── conversations/            # 对话记录目录
    │   ├── conversation-001.json
    │   └── conversation-002.json
    ├── patterns/                 # 模式卡目录
    │   ├── pattern-001.json
    │   └── pattern-002.json
    ├── reviews/                  # 回顾报告目录
    │   ├── review-001.json
    │   └── review-002.json
    └── deleted/                  # 已删除文件目录（级联删除后移到这里，可恢复）
        ├── insight-003.json
        └── ...
```

### 说明

- `outputs/` 目录已在 `.gitignore` 中排除，不会提交到 Git
- 每个用户一个目录，使用 `user_id` 隔离
- 已删除的文件移到 `deleted/` 目录，可在一定时间内恢复（当前未设置自动删除期限）
- 所有文件使用 JSON 格式存储
- 当前为未加密存储（`local_unencrypted`），高敏感内容建议不保存

---

## 9. 数据保留与删除规则

基于 `storage/README.md` 中的设计，并复用 diarygpt 的源—派生关系与删除失效经验：

1. **用户删除后立即级联删除**：用户要求删除单条或全部档案时，立即删除源条目及其所有派生物（摘要、索引、模式卡证据、洞察关联、回顾结论关联），不能只从界面隐藏。
2. **源—派生关系级联删除（复用 diarygpt 经验）**：
   - 删除对话记录时，级联删除所有 `source_conversation_ids` 包含该对话 ID 的洞察卡和模式卡
   - 删除洞察卡时，重新评估所有 `source_insight_ids` 包含该洞察卡 ID 的模式卡的证据门槛，证据不足则降为待验证或删除
   - 删除模式卡时，级联删除回顾报告中对该模式卡的引用
   - 删除生活风格画像时，级联删除所有相关的洞察卡、对话记录、模式卡、回顾报告
3. **删除后不可恢复（删除失效）**：删除后记录不可通过检索或模式证据访问，不能只从界面隐藏。已删除的文件移到 `deleted/` 目录，仅用于审计和用户主动恢复，不参与任何检索或分析。
4. **不设置自动删除期限**：除用户主动删除或平台规则要求外，不设置自动删除期限。用户不删除则保留。
5. **删除记录最小化**：删除记录只保留完成级联所需的最小元数据（如删除时间、删除的条目 ID），不保留被删除的原文或敏感理由。
6. **session_only 模式不持久化**：`session_only` 模式下，Skill 本身不持久化任何数据。

---

## 10. 下一步

第一步（数据结构设计）完成后，下一步：
1. 创建本地存储适配器（`storage/adapters/local_json.py`），实现抽象接口
2. 更新 SKILL.md 和工作流，增加持久化模式的说明
3. 创建测试脚本，验证存储适配器的读写功能

---

## 11. 加密存储设计

> 新增存储模式：`local_encrypted`（加密的本地存储）。
>
> **设计原则**：简单易用，不设计复杂的私密库、锁定机制等，只做基础的加密存储。所有个人信息与敏感内容放在一起加密存储。
>
> **复用经验来源**：
> - GitHub 上的密码管理器项目（多个）：使用 Fernet 对称加密（AES-128-CBC + HMAC-SHA256）、基于用户密码派生密钥（PBKDF2-HMAC-SHA256）、存储在 JSON 文件中

### 11.1 加密方式

| 项目 | 说明 |
|------|------|
| 加密算法 | Fernet 对称加密（AES-128-CBC + HMAC-SHA256） |
| 密钥派生 | PBKDF2-HMAC-SHA256，100000 次迭代 |
| 密钥长度 | 32 字节（256 位） |
| Salt 长度 | 16 字节（128 位），随机生成 |
| 库依赖 | `cryptography` 库（Python） |

### 11.2 加密的内容

**加密的用户数据文件：**
- `profile.json`（生活风格画像，全量版）
- `profile.lite.json`（生活风格画像，精简注入版）
- `insights/*.json`（洞察卡）
- `patterns/*.json`（模式卡）
- `conversations/*.json`（对话记录）
- `reviews/*.json`（回顾报告）
- `progress.json`（探索进度）
- `config.json`（用户配置）

**不加密的内容：**
- 密码验证信息（salt + password_hash），存储在单独的文件中
- SKILL.md、workflows/、references/、templates/ 等非用户数据

### 11.3 密码验证信息（不加密）

存储在 `auth.json` 文件中，不加密，用于验证用户密码：

```json
{
  "salt": "base64-encoded-salt",
  "password_hash": "base64-encoded-password-hash",
  "iterations": 100000,
  "algorithm": "PBKDF2-HMAC-SHA256",
  "created_at": "2026-09-06T10:00:00+08:00"
}
```

### 字段说明

| 字段 | 说明 |
|------|------|
| `salt` | 盐值，随机生成，base64 编码 |
| `password_hash` | 密码哈希，基于密码 + salt 派生，base64 编码 |
| `iterations` | PBKDF2 迭代次数，默认 100000 |
| `algorithm` | 密钥派生算法，固定为 PBKDF2-HMAC-SHA256 |
| `created_at` | 创建时间（ISO 8601 格式） |

### 11.4 加密文件格式

每个加密文件就是一个 Fernet token（base64 编码的字符串），解密后是 JSON 内容。

**文件扩展名**：保持 `.json` 扩展名，但内容是加密的 Fernet token。

**示例**：
```
gAAAAABh...（Fernet token，base64 编码）
```

### 11.5 存储目录结构（加密模式）

```
outputs/
└── {user_id}/                    # 每个用户一个目录
    ├── auth.json                 # 密码验证信息（不加密）
    ├── profile.json              # 生活风格画像（全量版，加密）
    ├── profile.lite.json         # 生活风格画像（精简注入版，加密）
    ├── config.json               # 用户配置（加密）
    ├── progress.json             # 当前探索进度（加密）
    ├── insights/                 # 洞察卡目录（加密）
    │   ├── insight-001.json
    │   └── insight-002.json
    ├── conversations/            # 对话记录目录（加密）
    │   ├── conversation-001.json
    │   └── conversation-002.json
    ├── patterns/                 # 模式卡目录（加密）
    │   ├── pattern-001.json
    │   └── pattern-002.json
    ├── reviews/                  # 回顾报告目录（加密）
    │   ├── review-001.json
    │   └── review-002.json
    └── deleted/                  # 已删除文件目录（加密）
        ├── insight-003.json
        └── ...
```

### 11.6 存储模式对比

| 模式 | 说明 | 加密 | 适用场景 |
|------|------|------|---------|
| `session_only` | 仅当前对话，不持久化 | 不适用 | 临时对话，不需要保存 |
| `local_unencrypted` | 未加密的本地存储 | ❌ | 信任本地环境，不需要加密 |
| `local_encrypted` | 加密的本地存储 | ✅ | 需要保护用户数据安全 |

### 11.7 密钥管理

1. **用户设置密码**：用户启用加密存储时，设置一个密码
2. **基于密码派生密钥**：使用 PBKDF2-HMAC-SHA256 从密码派生密钥
3. **密钥不存储**：密钥不存储在文件中，每次使用时基于密码派生
4. **密码验证**：密码验证信息（salt + password_hash）存储在 `auth.json` 中，用于验证密码
5. **密码修改**：用户可以修改密码，修改时需要用旧密码解密所有文件，然后用新密码重新加密

### 11.8 加密存储适配器接口

加密存储适配器实现与未加密存储适配器相同的接口（`storage/README.md` 中定义的抽象接口），只是在读写文件时增加加密/解密层。

**接口差异**：
- 初始化时需要用户密码（用于派生密钥）
- 增加 `verify_password(password)` 方法，用于验证密码
- 增加 `change_password(old_password, new_password)` 方法，用于修改密码
- 其他接口与未加密存储适配器相同

### 11.9 安全说明

1. **使用标准加密算法**：使用 Fernet（AES-128-CBC + HMAC-SHA256），不自己发明加密算法
2. **密钥派生**：使用 PBKDF2-HMAC-SHA256，100000 次迭代，防止暴力破解
3. **密码不存储**：密码本身不存储，只存储密码哈希
4. **用户控制**：用户可以选择是否启用加密，设置自己的密码
5. **局限性**：本地加密存储不能防止恶意软件读取内存中的密钥，也不能防止用户忘记密码后无法恢复数据
