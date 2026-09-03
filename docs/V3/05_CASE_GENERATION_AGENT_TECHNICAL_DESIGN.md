# V3.1 用例生成接入设计

> 新 V2 Conversation Agent 是控制入口；现有用例 Workflow 作为领域执行器复用。

## 1. 桥接而非重写

拟定工具：start_case_generation、get_case_generation_status、get_case_artifact。这些是 V3 计划名称，不是宣称当前已有端点。
start 校验来源与项目后创建旧业务 Run，立即返回 run_id/状态；不在一个模型工具调用内无限等待整个审批流程。
后续事件由平台持久化/推送；对话可按需读取状态，不让模型持续忙轮询。
业务 Run 与触发它的 conversation Run 分别记录、互相引用；幂等键包含触发消息与动作，避免重复创建。

## 2. 复用

保留现有 case_generation Workflow、T05 工具、确定性去重、coverage Artifact、审批和保存 Service。V3.1-T01 先检查当前合同与缺口，再写适配器。
两个现有生成场景配置继续服务领域 Workflow，通用 agent_chat 模型不自动替代它们。
Provider 空回复和格式问题单独诊断，不能以引入通用 Agent 自动宣布解决。

## 3. 边界

- 来源/候选/版本由服务端读取，不信任模型传入完整待保存数据。
- 人工保存仍走后端 Approval + 单事务；模型不能调用自批接口。
- 局部修正生成新 revision，并让旧审批失效或明确绑定旧版；具体合同在 T03 制定。
- 旧任务数据不改名、不删除；新入口可回退到旧生成页面。
- V2 新通用 Skill Catalog 默认不包含这些业务工具，V3 验收后显式启用。

原设计全文在 [旧技术设计](../archive/PRE_PI_V2_2026-09-03/05_CASE_GENERATION_AGENT_TECHNICAL_DESIGN.md)；使用时以本版桥接边界为准。
