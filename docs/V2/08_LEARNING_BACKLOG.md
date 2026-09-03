# TestMind Agent 待学习知识点

> 用途：先记录项目开发中需要理解的概念，不阻塞当前编码。
>
> 使用方式：遇到对应任务时再学习、实践和回填，不要求一次学完。

## 状态说明

- `待学习`：尚未系统学习
- `学习中`：正在结合当前任务理解
- `已实践`：已经在 TestMind 代码中实现并通过测试
- `需复习`：实现过，但还不能独立解释

## V2.1-T01 Baseline 测试

| 知识点 | 状态 | 对应实践 |
|---|---|---|
| pytest fixture | 已实践 | `backend/tests/conftest.py` 的 db_session：每条测试 drop_all/create_all 重建内存 SQLite |
| monkeypatch / Fake LLM | 已实践 | `test_function_case_generation_service.py` / `test_api_document_generation_service.py` 中 monkeypatch 服务模块命名空间的 LLM 函数 |
| 单元测试与集成测试区别 | 已实践 | Service 层单测与 permission_service 确定性规则测试；Router 集成测试留待后续任务 |
| Arrange-Act-Assert | 已实践 | 每条测试按 准备数据 → 执行 → 断言 组织 |
| Baseline | 已实践 | 冻结 V1 行为，发现"保存不规范化 priority"等当前事实并登记于开发记录 |
| 测试隔离 | 已实践 | 内存 SQLite + 每测试重建全部表，测试间零依赖 |

## V2.1-T02 数据库迁移与 Agent 数据模型

| 知识点 | 状态 | 对应实践 |
|---|---|---|
| Alembic upgrade/downgrade | 已实践 | `backend/alembic/versions/0002_agent_platform_tables.py` + `test_agent_platform_migration.py`：临时 SQLite 上 stamp/upgrade/downgrade/再 upgrade 全部验证 |
| 数据库 migration 与 create_all 区别 | 已实践 | 0001 no-op baseline + 0002 增量建表；create_all 过渡期保留，接管边界记录在开发记录 |
| AgentSession / AgentRun | 已实践 | `app/models/agent_session.py`、`agent_run.py`：一次对话 vs 一次任务的字段边界、heartbeat/幂等键 |
| AgentMessage / AgentEvent | 已实践 | `app/models/agent_message.py`、`agent_event.py`：(session_id, sequence_no) 唯一约束防乱序 |
| Artifact / Approval | 已实践 | `app/models/agent_artifact.py`、`agent_approval.py`：版本/状态/来源哈希与审批边界 |
| 幂等键和唯一约束 | 已实践 | `uq_agent_runs_idempotency(session_id, workflow_code, idempotency_key)`，NULL 不参与唯一性的语义测试 |
| 索引设计 | 已实践 | 外键/状态/心跳列索引（ix_agent_runs_status、ix_agent_runs_heartbeat_at 等），迁移测试断言 |

## V2.1-T03 LLM Gateway 与 Provider

| 知识点 | 状态 | 对应实践 |
|---|---|---|
| LLM Provider Adapter | 已实践 | `app/agents/providers/`：OpenAICompatibleAdapter（httpx）+ AnthropicAdapter（官方 SDK 1.3.0），统一 Protocol |
| System/User/Tool Message | 已实践 | `app/schemas/llm_gateway.py` 的 LLMMessage 与两个 Adapter 的映射（tool→tool_call_id / tool_result） |
| 结构化输出 | 已实践 | 两级降级 + 能力三态：原生 response_format 仅在 SUPPORTED 时启用，默认 JSON 提示约束 + Pydantic 本地校验 |
| Tool calling loop | 已实践（只解析） | LLMToolCall 解析与透传（tool_use 块 / choices.tool_calls），执行循环留给 Runtime |
| Timeout/Retry/Backoff | 已实践 | Gateway 内有限重试（max_retries=2、指数退避、sleeper 注入），SDK max_retries=0 防双重重试 |
| Token 与成本统计 | 已实践 | LLMResult 的 prompt_tokens/completion_tokens/duration_ms/request_id/finish_reason 采集 |
| Prompt 版本管理 | 待学习 | 尚未实现（留待 Workflow/T04 后接入） |

## V2.1-T04 Agent Runtime

| 知识点 | 状态 | 对应实践 |
|---|---|---|
| 有限状态机 | 已实践 | `app/agents/runtime/transitions.py`：合法转换集中定义，非法转换抛 InvalidStateTransitionError |
| Skill Registry | 已实践 | `app/agents/registry/skill_registry.py`：code 唯一、内存注册、Fake Skill 验证闭环 |
| Tool Registry | 已实践 | `app/agents/registry/tool_registry.py`：定义与注册，不执行、不动态 import |
| Worker 与任务队列 | 已实践 | `app/workers/agent_worker.py`：run_once/run_loop/recover_stale_runs + CLI，无 Celery/Redis |
| 原子抢占 | 已实践 | `agent_run_service.claim_queued_run`：条件 UPDATE + rowcount 判定，双 Session 竞争测试 |
| Heartbeat | 已实践 | 抢占即写 + 步骤边界 `on_step_boundary` owner-only 更新；stale → interrupted + `agent_worker_heartbeat_timeout` |
| Cancellation | 已实践 | `transitions.py` 支持 queued/running→cancelled；Runner 执行前检查 cancelled（拒绝继续） |
| GATE / Human-in-the-loop | 已实践 | `AgentRunner` 创建 pending Approval 后进入 waiting_approval，approve/reject/cancel/expire 仅 pending 可解决 |

## V2.1-T05/T06 用例生成 Skill

| 知识点 | 状态 | 对应实践 |
|---|---|---|
| 原子需求条款 | 已实践 | T05 `compute_coverage_matrix` 聚合 + T06 Workflow 拆解（模型建议 + 程序去重/格式校验） |
| 覆盖矩阵 | 已实践 | `case_validators.compute_coverage` 确定性聚合 + unknown_refs 警告，不接受模型自报覆盖率 |
| 确定性 Validator | 已实践 | `case_validators` 的 Schema/业务规则纯函数 + validate_case_schema / validate_case_business_rules 工具 |
| 用例去重 | 已实践 | `find_duplicates` 场景级确定性指纹（V2.1-T05.1：function=名称+步骤+预期+类型、api=method+canonical URL+body+预期+类型），SHA-256 安全摘要，已有用例 dedup_fingerprint 复用 |
| Agent 修正循环 | 已实践 | T06 repair_decision：只修正问题候选子集、替换候选 revision+1、最多 2 轮 |
| 停止条件 | 已实践 | T06 停止条件（无缺口 / repair_round==2 / llm_calls==4 / 零候选 failed / max_steps / 取消）集成测试验证 |
| Prompt Injection | 待学习 | 留 V2.3-T01 安全加固（工具权限已由 require_project_read 兜底，instructions 已声明业务数据不可信） |

## V2.1-T07/T08 对话与前端

| 知识点 | 状态 | 对应实践 |
|---|---|---|
| Session/Message/Event API | 已实践 | `agent_router.py`：会话/消息/事件端点，owner 权限与角色强制（user 不可伪造 assistant） |
| 异步任务 API | 已实践 | `POST /agent/runs/case-generation` 返回 202+run_id；Run 由 Worker 显式推进 |
| 前端轮询 | 已实践 | `useAgentSession.js`：queued/running 定时快照、终态停止、请求代次隔离、卸载清理、有界同步重试；浏览器恢复/取消/切换验证 |
| SSE | 待学习 | 后续优化实时事件流 |
| Artifact UI | 已实践 | `AgentArtifactPanel.jsx` + `agentContract.js`：嵌套候选、覆盖矩阵、服务端候选 ID、当前审批产物绑定、保存结果恢复；6 条合同测试及浏览器联调 |
| 前后端合同联调 | 已实践 | `09_FRONTEND_BACKEND_INTEGRATION.md`：真实 HTTP + 临时 SQLite + Fake LLM + 实际 Worker，区分接口通路与真实模型效果 |
| 审批幂等 | 已实践 | GATE 决议重复相同请求幂等（不重复事件）；保存幂等基于持久化 resolution_json，不同 candidate_ids 409 |

## V2.1-T09 Agent Eval

| 知识点 | 状态 | 对应实践 |
|---|---|---|
| Golden Dataset | 待学习 | 固定需求与接口文档样本 |
| Deterministic Grader | 待学习 | Schema、权限和轨迹门禁 |
| LLM Judge | 待学习 | 只作为业务质量补充 |
| Baseline/Ablation | 待学习 | one-shot 与 Agent 对比 |
| 轨迹评测 | 待学习 | 必须/禁止工具和部分顺序 |
| 稳定性测试 | 待学习 | 同输入重复运行 |
| 延迟与成本指标 | 待学习 | p50/p95、token、调用次数 |

## V2.2/V2.3 后续主题

| 知识点 | 状态 | 对应实践 |
|---|---|---|
| 执行快照和内容 Hash | 待学习 | 根因分析证据冻结 |
| AST 静态检查 | 待学习 | 检查生成代码但不执行 |
| 证据引用和置信度 | 待学习 | RCA Artifact |
| Secret 管理与脱敏 | 待学习 | 模型、MCP、数据库凭证 |
| 测试数据写入安全 | 待学习 | 造数 Skill Approval |
| 缺陷描述 Schema | 待学习 | defect_draft Artifact |

## 学习原则

1. 当前任务需要什么，只学习什么。
2. 每个知识点必须映射到 TestMind 的真实文件和测试。
3. “已实践”必须有代码和验证证据。
4. 不因为没有先学完全部概念而停止项目。
5. 每个开发任务完成后更新本文件状态。
