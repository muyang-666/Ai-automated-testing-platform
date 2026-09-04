# V3：更高级测试能力扩展

> 2026-09-04 重新划分。基础测试设计与用例协作编辑已成为 V2 的纵向闭环（Test Artifact + Artifact Tools + Test Design Skill），V3 不再承担“第一次接入用例生成”。
> V3 转向更高级测试能力，且都复用 V2 的 Conversation + Agent Loop + Tools + Artifact 模型，而不是为每个功能新建一个固定 Workflow Runtime。
> 前置：V2-P10 对话式 Test Artifact 闭环通过（[V2 README](../V2/README.md)）。

- [主计划](01_TEST_CAPABILITY_PLAN.md)：V3.1 API Testing、V3.2 Failure RCA、V3.3 Test Data、V3.4 Defect、V3.5 Execution / CI。
- [开发记录](02_DEVELOPMENT_RECORD.md)：新版本实际结果。
- [验收清单](03_ACCEPTANCE_CHECKLIST.md)：业务安全和效果。
- [旧开发证据](../archive/PRE_PI_V2_2026-09-03/02_DEVELOPMENT_RECORD.md)。

V3 的入口是 V2 的对话 Agent 按需加载领域 Skill / 调用领域 Tool，不是把每次聊天再次固定成生成任务。
