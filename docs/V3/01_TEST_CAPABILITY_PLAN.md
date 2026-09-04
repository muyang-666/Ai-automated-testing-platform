# V3 高级测试能力开发计划

> 前置：V2-P10（对话式 Test Artifact 闭环）通过，或用户明确授权有边界的隔离试验。默认不在 V2 基础开发期间并行扩展业务。
> 2026-09-04 调整：基础测试设计与用例协作编辑已经进入 V2（P07 Test Artifact、P08 Artifact Tools + Test Design Skill，见 [V2 新路线](../V2/12_POST_P04_DEVELOPMENT_PLAN.md)），V3 不再承担“第一次接入用例生成”。
> 本文件为新版本任务，旧编号只用于历史溯源，不重置已实现代码。

## 1. 版本与复用基础

| 新版本 | 目标 | 复用基础 | 备注 |
|---|---|---|---|
| V3.1 | API Testing Agent | V2 Conversation + Agent Loop + Tools + Artifact | 原“V3.1 用例生成”不再成立 |
| V3.2 | Failure RCA Agent | 同上 + V1 失败/执行证据 | 原根因分析 |
| V3.3 | Test Data Agent | 同上 | 原造数任务 |
| V3.4 | Defect Assistant | 同上 | 原缺陷任务 |
| V3.5 | Execution / CI Integration | 同上 + V1 执行与报告 | 新增 |

共同前提：持续 Conversation + Agent Loop + Tool Executor + Tool Policy 来自 V2；TestArtifact 的 artifact_type 可扩展到 api_test_design / rca_report / test_plan 等；领域能力以 Tool + Skill（领域知识 + 行为规则）挂载，而不是每个功能新写一套固定 Workflow Runtime。

通用权限、预算、上下文、恢复和审批属 V2；具体业务表、网络动作、外部系统、测试质量门禁属 V3。

## 2. 不再属于 V3 的内容

基础测试点 / 测试用例的生成、局部修正、查重、覆盖与人工协作编辑已在 V2 完成（Test Artifact + Artifact Tools + Test Design Skill）。旧的固定 case_generation Workflow 退役计划见 [V2 Legacy 迁移](../V2/16_LEGACY_WORKFLOW_MIGRATION_PLAN.md)。

## 3. V3.1 API Testing Agent

依据接口文档/OpenAPI 生成与维护 API 测试资产（请求、断言、场景串联），并基于 V2 内核准备真实执行。详细任务在 V2-P10 后按 V2 内核实际能力设计；本节占位，不在此虚构任务编号或承诺。

## 4. V3.2 Failure RCA

失败证据快照 → 确定性取证 → RCA 结论：

- V3.2-T01：运行证据快照与确定性解析（用执行时定义/代码/request/response，不拿当前代码冒充历史）。
- V3.2-T02：诊断 Skill、证据工具与验证（confirmed/likely/inconclusive；绑定证据，不强行猜根因）。
- V3.2-T03：Artifact（rca_report）+ 会话 UI 与质量评测。

## 5. V3.3 Test Data

- V3.3-T01：环境/数据规则/只读查询工具，优先查找和复用合成测试数据。
- V3.3-T02：受限造数动作、审批、幂等、审计、清理和业务验收。
- 环境白名单、限量和数据生命周期强制执行；禁止接受任意 SQL、生产写入或复制实习敏感数据。

## 6. V3.4 Defect

- V3.4-T01：输入事实与证据提取，生成结构化 defect_draft 和可复制描述。
- V3.4-T02：缺失信息追问、Artifact 编辑/版本及质量验收。
- 首期只产草稿，不自动提交外部缺陷系统；外部连接和发布权限另行授权。

## 7. V3.5 Execution / CI（占位）

连接既有 V1 测试执行与报告、CI 事件触发 Agent 化测试分析。详细设计待 V2-P10 后补充。

## 8. 统一业务规则

- 每个 Skill 注册 required_context、允许工具、预算、输入/输出和版本。
- 业务动作每次重新检查用户/项目/环境权限，不能信任聊天上下文里模型给出的身份。
- 长任务由领域 Worker/长时工具按合同运行，返回任务引用；对话请求完成不是业务任务完成。
- 保存/造数/重跑与外部提交均需审批；自然语言意图不能替代后端操作授权。
- 普通问答不要求业务 Artifact Schema；业务产物不合法时应解释并在预算内修正，不能当自由聊天成功。
- 每项收尾只跑新增/受影响测试；对应版本验收时才组织综合回归。
- 不凭旧测试数字宣称 V3 完成，不凭模型选工具正确宣称最终业务结果正确。

## 9. 历史资料

[旧主计划](../archive/PRE_PI_V2_2026-09-03/01_AGENT_DEVELOPMENT_PLAN.md)与[旧开发记录](../archive/PRE_PI_V2_2026-09-03/02_DEVELOPMENT_RECORD.md)保留原编号、事实和遗留。
这些资料只是参考：遇到与新 V2/V3 路线矛盾，以本目录和当前 V2 主计划为准。
