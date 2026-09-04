# V2 核心对象：从 Workflow 到对话 Agent

> 配合 [主计划](01_AGENT_DEVELOPMENT_PLAN.md) 按任务学习，不要求先学完所有概念。

| 对象 | 直观理解 | TestMind 的含义 |
|---|---|---|
| Session | 一间持续聊天的房间 | 持久化历史、owner 和可选项目 |
| ConversationTurn / Run | 处理你的一次请求 | 可包含多次模型和工具调用；有预算和终态 |
| ModelTurn | 问模型一次 | 返回文本、工具调用或错误 |
| Message | 说过的话/工具反馈 | 按角色和内容块保存，不能把进度混进去 |
| Agent Loop | 处理一轮请求的循环 | 模型→工具→结果→模型，直到回答或安全停止 |
| Tool | 受控的具体动作 | 有参数 Schema、权限和副作用声明 |
| Skill | 某类测试任务的做法 | 领域知识 + 行为规则（如 test-design），按需加载；不是固定 phase 状态机，也不是额外权限钥匙 |
| Workflow | 固定业务步骤 | 现有 case_generation Workflow 已退役为 legacy，不再作为新 Agent 主路径；确定性能力迁为 Tool/Service（见 16） |
| Event | 执行进度通知 | UI 流式增量/状态、Revision/Diff/Approval 事件，可用游标恢复 |
| Approval | 人的执行许可 | 绑定具体动作和参数，按动作风险出现（不是固定 gate）；模型不能自批 |
| Compaction | 工作上下文整理 | 保留原始历史与 Artifact Revision，只压缩提交模型的视图 |
| TestArtifact | 你和 AI 一起维护的测试资产 | 长期存在的测试点/用例树，Node / Revision / Operation / Diff / Undo / 乐观锁；脑图只是它的视图 |
| AgentArtifact | 一次 Run 的执行产物 | 旧的用例/覆盖候选快照（legacy/执行证据），不等于长期编辑的 TestArtifact |

例子：“帮我概括笔记”可以直接回答；“把登录这块展开成用例”“第二个不要”“按我刚改的写法把同组统一一下”是 Test Agent 围绕 TestArtifact 的持续编辑。普通聊天与 Artifact 编辑不绑死在同一个固定用例 JSON Schema。

先学 P01 消息合同，再学 P03 循环；已有 Python if/循环知识即可理解。难点主要是取消、并发、权限、持久化和不确定副作用，而不是把代码写成 while。
