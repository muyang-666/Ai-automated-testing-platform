# Legacy Workflow 退役与迁移计划（历史档案，2026-09-04）

> 本文件是 V2-P05 的临时实施计划档案。其有效内容（依赖审计、A/B/C 内容分类、legacy 兼容、数据库与测试迁移节奏、完成定义）已并入 [开发计划 V2-P05](../01_DEVELOPMENT_PLAN.md#v2-p05--conversation-runtime-收敛--legacy-workflow-退役)；P05 执行时以开发计划为准，本档案仅保留当时的完整推导与细节。
> 原目标：删除固定 Workflow 对新 Test Agent 的架构影响，同时避免一次性删除旧代码导致 V1 或历史数据不可用。

# 1. 当前问题

历史架构中存在：

```text
AgentRunner
→ workflow_code
→ CaseGenerationWorkflow
→ next_step
→ execute_step
```

这套机制早于 Pi-like Agent Loop。

在新 V2 中同时存在：

```text
ConversationRunner
→ Agent Loop
```

如果长期保留两套核心，会出现：

- 两个“谁决定下一步”的控制器；
- 两套 Tool 调用路径；
- 两套 Approval 语义；
- 两套 Run 恢复模型；
- 新功能不知道应该写 Tool 还是 Workflow Step；
- Case Generation 永远被固定流程绑住。

因此必须退役。

---

# 2. 迁移原则

不是简单：

```text
rm -rf workflow
```

而是：

```text
识别能力
→ 抽出确定性能力
→ 删除流程编排
→ 保留必要 legacy 兼容
→ 最终删除旧 Runner
```

---

# 3. 旧 Workflow 内容分类

逐项把旧 Step 分成三类。

## A. Domain Tool

例如：

```text
load_requirement
load_existing_cases
deduplicate
coverage
validate
save
```

迁移到 Tool / Service。

---

## B. LLM Prompt Knowledge

例如：

```text
如何分析测试点
如何生成边界
如何修正用例
```

迁移到：

```text
skills/test-design/SKILL.md
```

或者 prompt resource。

---

## C. Orchestration

例如：

```text
phase
next_step
retry phase
coverage_gate
repair loop
```

删除。

这些是旧架构真正要退役的部分。

---

# 4. P05 执行步骤

## Step 1：Dependency Audit

搜索：

```text
CaseGenerationWorkflow
AgentRunner
workflow_code
legacy_workflow
case_generation
next_step
execute_step
```

列出：

- API 调用方；
- Worker 调用方；
- tests；
- database values；
- frontend references。

没有审计前不物理删除。

---

## Step 2：新 Conversation 主路径禁止依赖 Workflow

保证：

```text
POST conversation turn
→ ConversationRunner
→ Agent Loop
```

任何测试请求也先进入 Agent Loop。

未来“生成用例”是自然语言意图，不是 Router hardcode。

---

## Step 3：抽取可复用能力

示例：

```text
CaseGenerationWorkflow._load_requirement()
```

若内部已有可靠 service，则 Tool 直接调用 service。

禁止：

```text
new_tool.execute()
→ CaseGenerationWorkflow.execute_step()
```

否则只是把 Workflow 藏进 Tool。

---

## Step 4：迁移 Prompt

将旧的：

```text
analyze prompt
generate prompt
repair prompt
```

拆成：

- Test Design Skill；
- 必要的小型 structured model tool/prompt；
- 不再绑定固定调用顺序。

---

## Step 5：处理历史入口

如果 V1 页面仍依赖：

```text
/runs/case-generation
```

两种选择：

### Option A：短期保留兼容

```text
legacy/
  case_generation/
```

明确标记：

```text
deprecated
not used by V2 conversation
```

P10 删除或继续作为 V1 compat。

### Option B：直接下线

仅当：

- 前端无调用；
- API 无调用；
- 数据迁移明确；
- 测试更新完毕。

---

# 5. 数据库迁移

P04 已引入：

```text
mode=conversation / legacy_workflow
workflow_code
```

不要立即为了“架构干净”破坏历史行。

推荐：

### P05

保留字段，停止新建 `legacy_workflow`。

### P07～P09

所有新 Test Agent 数据使用：

```text
conversation
TestArtifact
ArtifactRevision
```

### P10

统计是否仍存在真实 legacy 调用。

如果无调用：

- 删除 legacy Router / Runner；
- 数据保留只读可查询；
- schema 字段是否删除可另做 migration。

不要把“删除 Python Workflow 类”和“删数据库历史字段”强绑定为同一个提交。

---

# 6. Approval 迁移

旧：

```text
scope_gate
coverage_gate
save_gate
```

新：

```text
Tool Policy
```

例如：

```text
生成 3 条测试点
→ no approval

删除 50 条
→ approval

写入正式业务表
→ approval
```

迁移后 Gate 不再属于测试流程顺序。

---

# 7. 测试迁移

旧测试不要全部直接删除。

分类：

```text
workflow orchestration tests
→ 删除

domain algorithm tests
→ 移到 Tool / Service tests

prompt quality tests
→ Skill/Eval tests

legacy endpoint tests
→ compat tests（若仍保留）
```

---

# 8. 完成定义

只有满足以下条件才算 Workflow 退役：

- 新 Conversation 无 Workflow 路由；
- 新测试设计能力只通过 Agent Loop + Tools；
- Skill 不包含 phase 状态机；
- Artifact 修改独立于 Run phase；
- Tool Executor 是模型动作的统一门禁；
- Coverage/Dedup/Validation 可被单独调用；
- UI 不展示 Workflow phase；
- 旧调用方已删除或明确隔离；
- P01～P04 行为没有回归。

---

# 9. 最终目标结构

```text
backend/app/agents/
├─ conversation/
│  ├─ loop.py
│  ├─ runner.py
│  ├─ context.py
│  ├─ policy.py
│  └─ tool_executor.py
├─ providers/
├─ registry/
├─ skills/
│  └─ test-design/
├─ tools/
│  ├─ artifact/
│  ├─ requirement/
│  └─ quality/
└─ legacy/               # 可选，最终可删除
```

业务领域：

```text
backend/app/test_artifacts/
├─ models/
├─ schemas/
├─ services/
├─ repository/
└─ diff/
```

不要让 `agents/` 同时承担 Artifact 数据领域本身。

Agent 使用 Artifact；Artifact 不依赖 Agent。
