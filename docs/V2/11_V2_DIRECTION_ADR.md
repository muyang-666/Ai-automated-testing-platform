# V2 架构决策：从固定 Workflow 转向可持续编辑的对话式 Test Agent

> 状态：Proposed  
> 生效范围：V2-P05 及之后  
> 背景：V2-P01～P04 已完成 Agent Message / Provider / Agent Loop / Conversation Persistence 基础。  
> 本 ADR 用于替代“测试能力必须等到 V3、V2 仅做通用聊天外壳”的旧边界。

## 1. 决策摘要

TestMind V2 的目标调整为：

> 构建一个可持续对话、可持续读取和修改测试资产的 Test Agent。  
> 测试用例不再被视为一次 Workflow 的最终输出，而被视为类似代码文件的长期 Artifact。

V2-P05 之后不再以固定 `case_generation Workflow` 作为新 Agent 的核心控制方式。

新的核心关系为：

```text
User
  ↓
Conversation
  ↓
Agent Loop
  ↓
LLM decides next action
  ↓
Tool Call
  ↓
Policy / Schema / Permission / Budget
  ↓
Artifact Operation
  ↓
Artifact State / Diff / Version
  ↓
Tool Result
  ↓
Agent Loop continues
```

核心原则：

> Model controls sequence.  
> Program controls capability and safety.  
> Artifact stores the evolving result.

中文表述：

> 让模型决定“下一步做什么”，让程序保证“动作怎么安全、正确地执行”，让 Artifact 保存“我们共同做出了什么”。

---

## 2. 为什么废弃固定 Workflow 作为核心

旧 `case_generation` 思路类似：

```text
load_source
→ load_context
→ analyze
→ generate_points
→ generate_cases
→ validate
→ deduplicate
→ coverage
→ repair
→ save
```

该模式适合一次性生成任务，但不适合持续协作式测试设计。

真实测试过程并不固定，例如用户可能：

```text
先分析需求
→ 先列测试点
→ 删除部分测试点
→ 展开其中三个测试点
→ 手工修改一条用例
→ 让 AI 补边界场景
→ 再做去重
→ 暂时不保存
→ 第二天继续修改
```

也可能直接：

```text
读取已有用例
→ 找缺失场景
→ 修改 TC023
```

甚至：

```text
不要生成测试点，直接给现有脑图补 3 个异常场景。
```

如果继续用固定 Workflow，系统会不断增加：

- 分支；
- phase；
- gate；
- 特殊跳转；
- resume 规则；
- 不同生成模式。

最终 Workflow 会代替模型成为业务控制器，与“持续对话 Agent”目标冲突。

因此 V2 做出以下决定：

1. 新 Conversation Agent 不再进入固定测试 Workflow；
2. 测试设计路径由 Agent 根据当前上下文动态决定；
3. 确定性能力继续以 Tool 保留；
4. Skill 用于领域知识与行为指导，不用于编排固定状态迁移；
5. Artifact 成为长期业务对象，而不是某次 Run 的一次性输出。

---

## 3. Workflow 删除边界

### 3.1 要删除的

从 V2 新架构中删除以下概念的核心地位：

- `next_step()` 驱动的测试流程控制；
- `phase=generate/validate/repair/...` 作为 Agent 必经路径；
- “每次聊天都创建 case_generation Run”；
- Workflow 内直接决定下一步调用哪个 LLM 或哪个业务 Tool；
- 固定 Gate 位置，例如“coverage_gate 到了就必须审批”。

### 3.2 不删除的

以下能力仍保留，并迁移为独立 Tool / Service：

- 需求读取；
- 现有用例读取；
- 测试点/用例创建；
- 用例修改；
- 删除/移动节点；
- Schema Validation；
- Duplicate Detection；
- Coverage Analysis；
- 导出 XMind；
- 持久化；
- 权限判断；
- Approval；
- Budget；
- Cancellation；
- Audit。

即：

```text
旧：
Workflow decides validate after generate

新：
Agent decides whether validation is useful
       ↓
validate_test_artifact Tool
       ↓
deterministic validation
```

---

## 4. 新的 V2 核心对象

### 4.1 Conversation

表示用户与 TestMind 的持续会话。

负责：

- Message history；
- 当前绑定项目；
- 当前工作 Artifact；
- 当前加载 Skill；
- Context 构建；
- 多轮指代，例如“第二个不要”。

Conversation 不等于一次任务。

---

### 4.2 ConversationTurn

一次用户输入及其处理过程。

例如：

```text
用户：
把锁定时间的边界补完整
```

这个 Turn 内部可能包含多个 ModelTurn：

```text
ModelTurn 1 → read_artifact
ModelTurn 2 → read_requirement
ModelTurn 3 → add_node × 3
ModelTurn 4 → final response
```

---

### 4.3 TestArtifact

长期存在、持续编辑的测试资产。

它不是“模型回答附件”，而类似：

```text
code repository
document
design file
```

用户与 Agent 都可以修改它。

TestArtifact 需要具备：

- Stable ID；
- Revision；
- Structured Tree；
- Diff；
- History；
- Undo；
- Source Reference；
- Ownership / Project Boundary。

---

### 4.4 ArtifactOperation

Agent 不应每次重新生成完整 JSON。

Agent 应提交增量操作，例如：

```json
{
  "op": "update_node",
  "node_id": "TC-023",
  "expected_revision": 17,
  "patch": {
    "expected_result": "账号锁定 30 分钟"
  }
}
```

Operation 执行成功：

```text
revision 17
   ↓
operation
   ↓
revision 18
```

这样才能实现：

- Diff；
- Undo；
- 审计；
- 乐观并发；
- 人工编辑和 AI 编辑共存；
- 减少大模型误改无关内容。

---

### 4.5 Skill

V2 后续 Skill 定义调整为：

> 面向某类任务的领域知识、策略、检查清单与行为说明。

例如：

```text
test-design/
  SKILL.md

api-testing/
  SKILL.md

failure-analysis/
  SKILL.md
```

`test-design` 可以告诉 Agent：

- 考虑正向、异常、边界、状态转换；
- 优先增量修改现有 Artifact；
- 不要无理由重写整棵树；
- 修改前先读取相关节点；
- 大范围删除需要解释并触发 Approval。

Skill 不再包含：

```text
phase A → phase B → phase C
```

---

## 5. 新的架构分层

```text
┌──────────────────────────────────────┐
│              Frontend                │
│                                      │
│ Chat | MindMap | Diff | History      │
└──────────────────┬───────────────────┘
                   │
┌──────────────────▼───────────────────┐
│          Conversation Layer          │
│ Session / Message / Context / Turn   │
└──────────────────┬───────────────────┘
                   │
┌──────────────────▼───────────────────┐
│            Agent Runtime             │
│ Agent Loop / Provider / Tool Exec    │
│ Budget / Policy / Cancel / Approval  │
└──────────────────┬───────────────────┘
                   │
┌──────────────────▼───────────────────┐
│              Tools                   │
│ read / search / add / edit / delete  │
│ move / validate / coverage / export  │
└──────────────────┬───────────────────┘
                   │
┌──────────────────▼───────────────────┐
│          Artifact Domain             │
│ TestArtifact / Node / Revision       │
│ Operation / Diff / SourceRef         │
└──────────────────────────────────────┘
```

Skill 横向影响 Agent 的行为，但不成为控制循环。

---

## 6. 与 Pi 思路的关系

V2 继续参考 Pi 的部分：

- Message model；
- ToolCall / ToolResult；
- Agent Loop；
- Event；
- Provider boundary；
- Context handling；
- Skill 按需加载思路。

TestMind 自己重点建设：

- Test Artifact；
- Artifact editing tools；
- Diff / revision / undo；
- 项目与权限；
- Approval；
- Test domain Skills；
- Chat + MindMap collaborative UI。

因此 V2 的定位不再是“Python 版 Pi”，而是：

> 基于 Pi-like Agent Core 构建面向测试资产持续协作编辑的 Test Agent。

---

## 7. 产品一句话定义

推荐 V2 README 使用：

> TestMind V2 是一个面向测试人员的对话式 Test Agent 工作台。用户可以像使用 Coding Agent 修改代码一样，通过持续对话让 AI 读取、创建、修改、重构和检查测试资产，并以脑图等结构化视图实时协作。

内部设计口号：

> Test Cases as Code, Agent as Collaborator.

这里的 “as Code” 不要求用例一定是 Python，而是强调测试资产具有：

- 结构化；
- 可增量编辑；
- 可 Diff；
- 可版本化；
- 可审查；
- 可恢复；
- 可持续演进。

---

## 8. 非目标

V2 暂不追求：

- 多 Agent 协作；
- 任意 Shell；
- 任意宿主文件系统访问；
- 全量 Pi 插件兼容；
- 自动执行所有测试环境动作；
- 无边界的自主 Agent；
- 一次性把所有测试类型做完。

V2 首先完成一个纵向闭环：

```text
持续聊天
→ 打开/创建测试 Artifact
→ AI 读取
→ AI 增量编辑
→ UI 脑图实时展示
→ 展示 Diff
→ 用户继续对话修改
→ Revision 可恢复
```

这个闭环完成后，再继续扩展 API Testing、RCA、造数等能力。
