# V3 开发记录

> 2026-09-03：完成版本重规划；未执行 V3 新任务。
> 2026-09-04：V3 重新划分 —— 基础测试设计与用例生成进入 V2（Test Artifact 纵向闭环），V3 转向 API Testing / Failure RCA / Test Data / Defect / Execution 等更高级测试能力，均复用 V2 Conversation + Agent Loop + Tools + Artifact。

| 版本 | 状态 | 复用基础 / 既有资产 |
|---|---|---|
| V3.1 API Testing | 待 V2 验收后规划 | V2 Artifact/工具；V1 接口文档生成服务可作能力来源 |
| V3.2 Failure RCA | 待实施 | V1 失败日志/场景数据可供后续证据设计 |
| V3.3 Test Data | 待实施 | 无新的造数 Skill |
| V3.4 Defect | 待实施 | 无新的缺陷 Skill |
| V3.5 Execution / CI | 待规划 | V1 执行与报告 |

旧的固定 case_generation Workflow 及其用例资产不再作为 V3.1 的接入对象：其退役/能力抽取按 [V2 Legacy 迁移](../V2/16_LEGACY_WORKFLOW_MIGRATION_PLAN.md) 处理；历史代码是否可复用由 V2 P07/P08 抽取工具时审计，不自动继承“新内核已接通”状态。

历史证据在 [旧开发记录](../archive/PRE_PI_V2_2026-09-03/02_DEVELOPMENT_RECORD.md)。其空响应/场景绑定/外键问题是当前复用风险，不因任务后移而标记解决。

每次新增记录须包含：任务编号、实际文件、复用内容、真实模型/数据授权范围、实际测试、业务副作用、未解决事项。
