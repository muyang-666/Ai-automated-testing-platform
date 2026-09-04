# V2 现有文档修改清单

> 用途：告诉后续 Codex / Claude 应该如何修改现有 V2 文档，避免新旧路线同时存在造成矛盾。
> 执行状态：2026-09-04 已按本清单完成文档迁移（见 README / 01 / 03 / 04 / 06 / 07 / 08 / 09 / 10 与 PROJECT_RECORD、V3、根 README 的实际修改）。本文件保留为历史迁移记录，不再作为待办指令。

# 1. README.md

当前旧表述需要替换：

```text
V2：通用 Python Agent 基础
V3：再做用例生成
```

改为：

```text
V2：
Pi-like Agent Core
+ 持续对话
+ Test Artifact
+ Artifact Editing Tools
+ Chat / MindMap / Diff

V3：
API Testing / RCA / Test Data / Defect / Execution 等高级测试能力
```

推荐标题：

```text
V2：对话式 Test Agent 与可持续测试资产工作台
```

---

# 2. 01_AGENT_DEVELOPMENT_PLAN.md

保留 P01～P04 原验收记录。

替换：

```text
## 1. V2 交付定义
```

新定义：

> 登录后用户可持续与 Agent 对话，并可创建或打开测试 Artifact。Agent 可以根据用户当前意图自主决定直接回复、读取资料、加载 Skill 或调用 Artifact Tool。测试设计不存在强制固定路径；用户可以先生成测试点、直接补用例、修改现有用例、检查覆盖或进行局部重构。所有测试资产修改以增量 Operation 产生 Revision 和 Diff，并实时反映到脑图工作区。

删除旧：

```text
不是 V2：
* 测试用例生成...
```

改为：

```text
V2 做“测试设计 Artifact 协作编辑”这一条基础纵向闭环，
但不在 V2 扩展 API 执行、RCA、造数、缺陷生成等高级领域能力。
```

将 P05～P10 替换为 `12_POST_P04_DEVELOPMENT_PLAN.md` 中的新路线。

---

# 3. 04_AGENT_SHELL_PRD.md

文件建议重命名或扩展为：

```text
04_CONVERSATIONAL_TEST_AGENT_PRD.md
```

产品目标从：

```text
先成为一个可持续交流、按需使用能力的 Agent，再扩展测试业务
```

改为：

> 成为一个可持续交流并围绕测试 Artifact 持续协作的 Test Agent。用户能够像使用 Coding Agent 修改代码一样，用自然语言让 Agent 读取、创建、修改、删除、重构和检查测试用例，同时可以直接在脑图中人工编辑。

新增核心用户故事：

```text
先列测试点
→ 展开某个分支
→ 用户人工修改
→ AI 根据修改继续
→ 查看 Diff
→ Undo
```

---

# 4. 06_TEST_AGENT_PLATFORM_ARCHITECTURE.md

删除/修改旧组件：

```text
Legacy Workflow Runner（兼容旧业务，不作为新对话入口）
```

新架构改为：

```text
ConversationRunner
→ Agent Loop
→ Artifact Tools
→ TestArtifact Domain
```

若 P05 仍需临时 legacy，画在旁路：

```text
Legacy API → Legacy Runner
```

不要与新 Agent 主链并列为同级核心。

修改对象说明：

旧：

```text
产物：V2 只预留引用合同，测试候选/覆盖矩阵在 V3。
```

新：

```text
TestArtifact 是 V2 的一等业务对象。
AgentArtifact 可保留为执行产物/历史兼容，但长期测试设计由 TestArtifact + Revision 管理。
```

Workflow 定义改为：

```text
Workflow 不再是 V2 Agent Core 的业务控制方式。
必要的确定性内部流程只能存在于 Tool/Service 内部，不控制整轮 Agent 对话路径。
```

---

# 5. 03_ACCEPTANCE_CHECKLIST.md

新增验收域：

## Artifact

- [ ] Artifact 可独立创建
- [ ] Tree 可读取
- [ ] 单节点更新
- [ ] Batch operation 原子
- [ ] Revision conflict
- [ ] Diff
- [ ] Undo
- [ ] owner/project isolation

## Conversational Editing

- [ ] 先测试点后用例
- [ ] 直接补用例
- [ ] 修改指定节点
- [ ] “第二个不要”指代
- [ ] 人工编辑后 AI 读取最新版
- [ ] 不固定执行 coverage/dedup
- [ ] Agent 不重写无关分支

## UI

- [ ] Chat / MindMap 同步
- [ ] Diff 可见
- [ ] Refresh 恢复
- [ ] Revision History
- [ ] Approval 显示真实影响范围

---

# 6. 08_LEARNING_BACKLOG.md

P05 后学习内容建议改成：

```text
P05
Worker lease / fencing / cancellation

P06
SSE / conversation runner

P07
Domain modeling
Event sourcing vs revision log
Optimistic locking
Tree data model

P08
Tool design
Patch semantics
Agent editing patterns
Skill design

P09
MindMap UI
Diff UX
Optimistic UI / conflict handling

P10
Context compaction
Long-lived artifact context
Approval by action risk
Recovery
```

---

# 7. V3 文档

V3 当前“V3.1 用例生成接入”应废弃。

改为：

```text
V3.1 API Testing
V3.2 Failure RCA
V3.3 Test Data
V3.4 Defect Assistant
V3.5 Test Execution / CI
```

原因：

> 基础测试设计/用例生成已经成为 V2 Artifact Agent 的核心纵向用例，不应再到 V3 才第一次接入。

---

# 8. 文档阅读顺序建议

调整后：

```text
README
↓
01_AGENT_DEVELOPMENT_PLAN
↓
11_V2_DIRECTION_ADR
↓
12_POST_P04_DEVELOPMENT_PLAN
↓
13_TEST_ARTIFACT_CASE_TREE_DESIGN
↓
14_ARTIFACT_TOOL_AND_AGENT_PROTOCOL
↓
15_CHAT_MINDMAP_DIFF_PRODUCT_DESIGN
↓
16_LEGACY_WORKFLOW_MIGRATION_PLAN
↓
10_PI_SOURCE_AUDIT
```

Pi Source Audit 继续负责 Agent Core 对照。

Artifact / MindMap / Diff 属于 TestMind 自研业务层，不需要硬找 Pi 一一对应。
