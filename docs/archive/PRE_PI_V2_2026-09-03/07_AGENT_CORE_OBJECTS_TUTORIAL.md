# TestMind Agent 四个核心对象学习笔记

> 学习主题：AgentSession、Skill、Tool、Artifact
>
> 学习阶段：V2.1 架构入门
>
> 状态：概念学习，不进入代码实现

## 1. 先记住一句话

```text
AgentSession = 一间持续存在的测试工作室
Skill        = 一份测试任务 SOP
Tool         = 能真正读取或操作系统的受控工具
Artifact     = Agent 产出的结构化业务成果
```

四个对象连起来：

```text
用户在 Session 中提出目标
→ Agent 选择 Skill
→ Skill 按流程调用 Tool
→ Tool 返回真实数据
→ Agent 生成或更新 Artifact
→ 用户确认 Artifact
→ 必要时调用写 Tool 保存
```

## 2. 贯穿示例

假设用户在 TestMind 中打开“登录功能需求”，输入：

```text
帮我根据这个登录需求生成测试用例，重点覆盖账号锁定。
```

系统需要完成：

1. 记住当前用户、项目、需求和此前对话。
2. 判断这属于“用例生成”。
3. 读取需求和已有用例。
4. 规划覆盖范围。
5. 生成和校验候选。
6. 展示覆盖矩阵和候选表格。
7. 等待用户确认后保存。

这七件事分别由四个核心对象协作完成。

## 3. AgentSession

### 3.1 它是什么

AgentSession 是用户与测试 Agent 的一次持续工作空间。

可以把它理解成：

> 一个带项目权限、对话记录、当前任务和业务上下文的聊天室。

### 3.2 它负责记录什么

- 谁在使用：user_id
- 在哪个项目：project_id
- 当前使用哪个 Agent 版本
- 用户和 Agent 的消息
- 当前正在执行哪个 Skill
- 已经产生哪些 Artifact
- 当前是否等待用户确认
- 会话创建和最后活动时间

### 3.3 它不负责什么

Session 不应该直接实现：

- 需求拆解算法；
- 数据库查询；
- 用例校验；
- 用例保存；
- 某个业务 Skill 的详细步骤。

它是容器，不是业务逻辑本身。

### 3.4 TestMind 示例

```json
{
  "session_id": 1001,
  "user_id": 8,
  "project_id": 3,
  "status": "active",
  "current_skill": "case_generation",
  "context": {
    "requirement_id": 12
  }
}
```

用户关闭页面后再次回来，只要 Session 还在，就能继续查看对话、GATE 和 Artifact。

### 3.5 Session 和 Run 的区别

虽然本轮重点是四个对象，但需要顺便认识 AgentRun：

```text
Session = 一次持续对话
Run     = 对话中执行的一次具体任务
```

例如同一个 Session 中可以有：

```text
Run 1：根据需求生成第一版用例
Run 2：补充账号锁定边界用例
Run 3：保存用户选中的候选
```

不要把 Session 和 Run 设计成同一张表。

## 4. Skill

### 4.1 它是什么

Skill 是一个测试领域能力包。

可以把它理解成：

> 一份既给模型看、也给程序执行的标准作业流程。

### 4.2 Skill 包含什么

- Skill 名称和版本
- 什么时候触发
- 需要哪些上下文
- 分几个 Phase
- 哪些步骤需要用户确认
- 允许使用哪些 Tools
- 输入输出 Schema
- Prompt 和领域规则
- 最大步骤和停止条件
- 如何评测结果

### 4.3 它不是单纯的 Prompt

错误理解：

```text
Skill = 一段很长的提示词
```

正确理解：

```text
Skill
= Instructions
+ Workflow
+ Tools Allowlist
+ Input/Output Schema
+ GATE
+ Stop Conditions
+ Evaluator
```

### 4.4 TestMind 示例

`case_generation` Skill 可以定义：

```text
Phase 0：确认需求来源和生成范围 [GATE]
Phase 1：读取上下文并生成覆盖计划 [GATE]
Phase 2：生成候选用例
Phase 3：校验、去重和覆盖检查
Phase 4：针对缺口有限修正
Phase 5：生成 Artifact，等待保存审批 [GATE]
```

允许的 Tools：

```text
load_requirement
list_existing_cases
validate_case_schema
deduplicate_cases
compute_coverage_matrix
save_selected_candidates
```

### 4.5 Skill 应该如何保存

建议：

```text
backend/app/agents/skills/case_generation/
  skill.yaml          机器可读配置
  instructions.md     给模型看的规则
  workflow.py         状态机和 GATE
  schemas.py          输入输出结构
  prompts/            分节点 Prompt
  evaluators.py       评测逻辑
```

## 5. Tool

### 5.1 它是什么

Tool 是 Agent 可以调用的受控 Python 函数或外部服务。

可以把它理解成：

> Agent 的手，但每只手都有明确权限和使用说明。

### 5.2 为什么需要 Tool

LLM 自己不能可靠知道：

- 数据库中有哪些已有用例；
- 当前需求的真实内容；
- 用户是否有项目权限；
- 某条候选是否重复；
- 用例是否已经保存。

这些需要 Tool 从 TestMind 的真实系统中读取或执行。

### 5.3 工具调用过程

```text
Agent/Skill 请求：list_existing_cases
→ 后端校验参数
→ 后端校验用户项目权限
→ 后端执行 SQLAlchemy 查询
→ 限制返回字段和数量
→ 脱敏
→ 返回结构化结果
→ Agent 根据结果继续工作
```

LLM 不会获得数据库连接，也不会直接执行 SQL。

### 5.4 Tool 的必要属性

| 属性 | 含义 |
|---|---|
| name | 工具名称 |
| description | 何时使用、返回什么 |
| input_schema | 参数格式 |
| output_schema | 返回格式 |
| read_only | 是否只读 |
| required_permission | 所需权限 |
| requires_approval | 是否需要人工确认 |
| idempotent | 重复调用是否安全 |
| timeout | 最大执行时间 |
| retry_policy | 哪些错误可以重试 |

### 5.5 只读 Tool 与写 Tool

只读 Tool：

```text
load_requirement
list_existing_cases
compute_coverage_matrix
```

通常可以自动执行，但仍要校验权限。

写 Tool：

```text
save_selected_candidates
create_test_data
submit_defect
rerun_test
```

默认需要人工审批，不能由模型自行决定执行。

## 6. Artifact

### 6.1 它是什么

Artifact 是 Agent 产生的结构化业务成果。

可以把它理解成：

> Agent 交付给测试人员审核、编辑、保存或下载的正式工作产品。

### 6.2 为什么不能只用聊天消息

聊天消息适合解释：

```text
我发现账号锁定时间的边界场景还没有覆盖。
```

但不适合承载：

- 30 条候选用例；
- 覆盖矩阵；
- 批量勾选状态；
- 每条用例的版本和来源；
- 保存结果。

这些应该存成 Artifact。

### 6.3 TestMind Artifact 类型

```text
coverage_matrix       覆盖矩阵
test_case_set         候选用例集
data_fabrication_plan 造数计划
defect_draft          缺陷描述草稿
root_cause_report     根因分析报告
execution_report      执行报告
```

### 6.4 Artifact 应记录什么

- artifact_id
- session_id
- run_id
- artifact_type
- version
- status：draft/reviewing/approved/saved/rejected
- payload_json
- source_refs
- source_hash
- created_by
- created_at / updated_at

### 6.5 Artifact 版本示例

```text
test_case_set v1：Agent 首次生成 18 条
test_case_set v2：用户要求补充账号锁定边界，新增 4 条
test_case_set v3：用户删除 2 条重复候选
```

最终保存时，系统应明确保存的是哪个 Artifact 版本。

## 7. 四个对象如何协作

完整示例：

```text
1. 用户进入 AgentSession 1001

2. 用户说：
   “根据需求 12 生成登录测试用例”

3. Skill Router 选择：
   case_generation v1

4. Skill 进入 Phase 0：
   展示来源和范围，等待用户确认

5. Skill 调用只读 Tools：
   load_requirement
   list_existing_cases

6. Skill 生成覆盖计划 Artifact：
   coverage_matrix v1

7. 用户确认覆盖计划

8. Skill 生成和校验候选，创建：
   test_case_set v1

9. 用户说：
   “补充第 4/5 次密码错误边界”

10. 同一 Session 启动新的 refine Run，更新为：
    test_case_set v2

11. 用户勾选并确认保存

12. 系统调用写 Tool：
    save_selected_candidates

13. Artifact 状态变成 saved
```

## 8. 对象关系图

```text
AgentSession
  ├─ AgentMessage
  ├─ AgentRun 1 ──使用──> Skill: case_generation
  │                 ├─调用──> Tool: load_requirement
  │                 ├─调用──> Tool: list_existing_cases
  │                 └─产生──> Artifact: coverage_matrix v1
  │
  ├─ AgentRun 2 ──使用──> Skill: case_generation/refine
  │                 └─产生──> Artifact: test_case_set v2
  │
  └─ AgentRun 3 ──调用──> Tool: save_selected_candidates
                    └─更新──> Artifact: saved
```

## 9. 最容易混淆的地方

### 9.1 Session 不是 Skill

- Session 负责持续对话和上下文。
- Skill 负责某类任务如何完成。

### 9.2 Skill 不是 Tool

- Skill 是流程。
- Tool 是流程中可调用的具体能力。

例如“用例生成”是 Skill，“查询已有用例”是 Tool。

### 9.3 Message 不是 Artifact

- Message 用于交流和解释。
- Artifact 用于保存结构化业务成果。

### 9.4 LLM 不执行 Tool

LLM 只提出结构化工具请求；真正执行的是 TestMind 后端。

### 9.5 Artifact 不等于已保存业务数据

候选用例 Artifact 仍然是草稿。只有用户批准并调用保存 Tool 后，才进入 `function_cases` 或 `api_cases`。

## 10. 首期数据库映射草案

| 对象 | 首期存储方式 |
|---|---|
| AgentSession | `agent_sessions` 表 |
| Message | `agent_messages` 表 |
| Skill | 代码目录 + `skill.yaml`，暂不存数据库 |
| Tool | Python 注册表，暂不存数据库 |
| Artifact | `agent_artifacts` 表 |
| Run | `agent_runs` 表 |
| Step/Event | `agent_steps` / `agent_events` 表 |
| Approval | `agent_approvals` 表 |

这只是概念草案。正式字段需要在下一轮学习“Session、Run、Message、Event 的数据库边界”后确定。

## 11. 本轮掌握标准

能够独立解释下面四句话：

1. Session 为什么不能和 Run 合并？
2. Skill 为什么不只是一段 Prompt？
3. Tool 为什么不能把数据库连接直接交给模型？
4. Artifact 为什么不能只保存在聊天消息中？

## 12. 小练习

场景：

```text
用户在登录需求页面点击“交给 Agent”，然后说：
“生成测试用例，但先不要保存，重点覆盖账号锁定。”
```

请判断：

1. 当前需求 ID 和 project_id 应该放在哪个对象？
2. “先确认范围，再规划覆盖，再生成”的流程属于哪个对象？
3. 查询已有登录用例属于哪个对象？
4. 最终的覆盖矩阵和候选用例表属于哪个对象？
5. 用户补充“再加第 4 次密码错误不锁定”时，应继续原 Session，还是创建全新 Session？

## 13. 下一课

下一轮学习：

> AgentSession、AgentRun、AgentMessage、AgentEvent 分别如何落数据库，以及一次对话怎样安全恢复。


