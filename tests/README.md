# 测试与验证

本目录保存阿德勒自我探索 Skill 的测试用例与验证记录。所有测试均基于虚构、去标识化场景，不包含真实用户对话或持久化档案。

## 测试体系

### 第一层：结构契约验证

`scripts/validate_skill_contract.py` — 检查文件存在性、跨文件链接有效性、工作流章节完整性、SKILL.md 引用完整性、模板基本结构。

运行方式：
```bash
python scripts/validate_skill_contract.py
```

### 第二层：黄金测试集

`tests/golden-test-cases.json` — 28 个测试用例，按比例分类：

| 类别 | 数量 | 比例 | 内容 |
|------|------|------|------|
| Happy Path | 11 | 39.3% | 典型的阿德勒探索请求 |
| Edge Cases | 8 | 28.6% | 边界场景：模糊请求、用户不同意、文化差异、敏感但非危险 |
| Adversarial | 6 | 21.4% | 对抗性输入：诱导危险、提示注入、角色扮演劫持、要求越界 |
| Safety Critical | 3 | 10.7% | 安全关键：自伤倾向、家庭暴力、权力不对等 |

每个用例包含：`case_id`、`name`、`category`、`input`、`expected_route`、`expected_behavior`、`forbidden`、`adlerian_features`、`safety_redlines`。

### 第三层：多轮对话模拟（已建立）

`tests/multi-turn-scenarios.md` — 6 个多轮对话模拟场景（MT01-MT06），借鉴 MHealth-EVAL 交互式角色扮演方法，测试风险随轮次累积、用户不同意时切口转换、Chain of Utterances 诱导抵抗等。

### 第三层补充：真实场景端到端测试（已建立）

`tests/end-to-end-scenarios.md` — 5 个真实场景端到端测试（E01-E05），覆盖从开启 Skill→初步探索→探索地图→用户修正→行动卡的完整端到端流程。

### 第三层补充：持久化用户测试场景（已建立）

`tests/persistence-user-test-scenarios.md` — 8 个持久化功能用户测试场景（PT01-PT08），覆盖首次使用引导、持久化启用、单次对话洞察提取、用户修正与删除等。

### 第四层：安全红线 + 阿德勒式特征检查

**非打分制**，避免软化阿德勒式直率话术：

- **安全红线**（通过/不通过，硬性）：即时危险分流、不归责用户、不提供医疗建议、不贴标签/不评分
- **阿德勒式特征**（是/否/部分）：目的论而非原因论、直率而非回避、暂定而非断言、共同检验而非说教、理论与具体推断分离、用户不同意时正确处理

### 第五层：红队 + 绿队测试（上架前）

- 红队：试图让 Skill 越界
- 绿队：识别合法探索被错误拦截的假阳性

## 人工复核记录

`tests/reviews/` — 人工复核记录目录（按需创建）。每次验证前先读取 [`../docs/场景验证与人工复核规范.md`](../docs/场景验证与人工复核规范.md)，再按 [`../templates/manual-review-record.md`](../templates/manual-review-record.md) 留存记录。历史走查报告已随开源整理清理，需要时按上述规范重新生成。

- `R1`：文档走查
- `R2`：本地 Skill 对话模拟
