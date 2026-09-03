# TestMind V2 Agent 开发主计划

> 文档用途：供 Claude Code 直接读取并按任务编号实施代码。
>
> 当前状态：仅完成规划，尚未开始 V2 代码实现。
>
> 版本路线：V2.1 对话 Agent Shell + 用例生成 Skill → V2.2 根因分析 Skill → V2.3 测试 Skill 扩展与细节优化 → V2.4 待定。

## 0. Claude Code 执行协议

### 0.1 角色分工

- 用户与 Codex 负责产品范围、技术方案、任务拆分和最终验收。
- Claude Code 负责用户明确指定任务的源码检查、编码、测试和开发记录。
- Claude Code 不负责自行改变产品方向或提前实现后续版本。

### 0.2 每次任务开始前必须执行

1. 阅读 `docs/PROJECT_RECORD.md`。
2. 阅读本文件。
3. 阅读 `docs/V2/06_TEST_AGENT_PLATFORM_ARCHITECTURE.md`。
4. 当前任务属于 V2.1 时，阅读 `docs/V2/04_CASE_GENERATION_AGENT_PRD.md`。
5. 当前任务属于 V2.1 时，阅读 `docs/V2/05_CASE_GENERATION_AGENT_TECHNICAL_DESIGN.md`。
6. 阅读 `docs/V2/02_DEVELOPMENT_RECORD.md`，确认真实进度和遗留问题。
7. 阅读 `docs/V2/03_ACCEPTANCE_CHECKLIST.md` 中与当前版本相关的门禁。
8. 检查 `git status --short`，保留用户已有修改。
9. 只读检查当前任务涉及的源码，不做全仓库无目的扫描。
10. 在修改前输出简短实施摘要：
   - 当前任务编号和目标；
   - 对现有代码的事实判断；
   - 准备新增/修改的完整文件列表；
   - 验证命令；
   - 风险和回滚方式。
11. 如果任务范围、文件边界、依赖和外部操作都符合用户已发送的单任务提示词，输出摘要后直接编码，不等待二次确认。

### 0.3 实施规则

- 一次只执行一个任务编号，例如 `V2.1-T03`。
- 用户将 Codex 生成的单任务提示词交给 Claude Code，即视为已经授权该提示词范围内的实现和非破坏性验证。
- Claude Code 完成只读核验和简短实施摘要后直接编码，不需要再次等待确认。
- 不得把多个任务合并为一次大改造。
- 不得修改当前任务文件范围之外的文件；确有必要时先停止并说明原因。
- 新实现必须保留 V1 旧接口或 feature flag，直到当前版本完成影子评测。
- 数据库变化必须提供 Alembic 迁移和回滚，不依赖 `Base.metadata.create_all()` 修改已有表。
- 所有工具输入和 LLM 结构化输出使用 Pydantic 校验。
- 不允许 Agent 获得任意 SQL、Shell、文件系统或任意 URL 工具。
- 不允许自动保存生成用例，不允许自动重跑有副作用的请求。
- 不记录隐藏思维链；只记录可观察步骤、工具、脱敏摘要和验证结果。
- 不把未执行的测试写成通过，不编造数量、覆盖率或性能提升。
- 只有新增依赖、真实环境或网络操作、数据库范围变化、破坏性操作、任务越界或无法安全合并用户修改时才暂停询问。

### 0.4 每次任务结束必须执行

1. 运行当前任务约定的单元测试、集成测试或前端构建。
2. 运行受影响的 V1 回归测试。
3. 检查数据库迁移的 upgrade/downgrade（如涉及）。
4. 输出实际修改文件、实际命令、真实结果和未解决问题。
5. 更新 `docs/V2/02_DEVELOPMENT_RECORD.md` 对应任务记录。
6. 只有在证据完整时，才能把任务状态改为“已完成”。

## 1. 产品目标

### 1.1 V2 总目标

在不破坏 V1 自动化测试闭环的前提下，把以下两条 one-shot LLM 链路改造成受控 Agent：

1. 需求文本/接口文档 → 测试用例。
2. 测试失败记录 → 结构化根因结论。

Agent 的价值必须来自：

- 主动读取授权范围内的业务上下文；
- 调用白名单领域工具；
- 使用确定性规则校验模型结果；
- 根据缺口进行有限修正；
- 输出可追踪证据；
- 遵守人工审批和资源上限。

只增加 Prompt 次数，不算完成 Agent 改造。

### 1.2 非目标

V2.1–V2.3 不做：

- 多 Agent 协作或 Agent swarm；
- 长期跨项目记忆；
- 向量数据库和完整 RAG 平台；
- 任意 SQL、Shell、网页或文件工具；
- Kubernetes 或微服务拆分；
- 自动保存全部候选用例；
- 未审批的自动重跑；
- 无限反思和无限修复循环。

## 2. 当前代码事实

Claude Code 实施前必须用源码重新确认，以下是规划时的事实基线：

### 2.1 用例生成

- 功能用例生成入口：`backend/app/services/function_case_generation_service.py`。
- 接口用例生成入口：`backend/app/services/api_document_generation_service.py`。
- 两条链路当前都是：读取单个来源 → 拼 Prompt → 调用一次 LLM → JSON 修复/基础校验 → 前端预览 → 人工保存。
- `generate_count` Schema 已存在，但当前实际生成数量主要由模型自行决定。
- 接口文档的结构化 headers/params/body/response 字段没有被完整用于生成上下文。
- 当前没有历史用例检索、覆盖矩阵、去重、缺口修正、Agent 状态和运行轨迹。
- `backend/app/services/ai_service.py` 当前主要是确定性 pytest 规则生成，不是 LLM 用例生成入口；其中的上下文规范化和代码校验可作为只读工具复用。

### 2.2 失败分析

- 入口：`backend/app/services/analysis_service.py`。
- 当前把 APICase、TestRun、日志、响应和当前生成代码拼入一个 Prompt，调用一次 LLM。
- 输出是自由文本，风险等级依赖正则提取。
- 分析旧运行时读取当前用例和当前代码，不是运行时冻结快照。
- `TestRun` 缺少实际请求快照、code hash、exit code、duration、runner/parser version 等证据。
- `SceneStepRun` 已有实际请求、响应、断言和变量提取，但当前失败分析没有使用。
- 配置中心有 `failure_analysis` 场景，现有分析服务仍绕过统一 LLM Client。

### 2.3 基础设施

- 后端：FastAPI、同步 SQLAlchemy、MySQL、Pydantic、httpx、pytest。
- 前端：React、Vite、Axios、Ant Design。
- 模型配置：LLM Provider、Model、Scene Config 已存在。
- 当前依赖 `Base.metadata.create_all()`，没有正式迁移链路。
- 当前没有独立的 Agent/平台测试目录，`tests_generated` 是测试产物，不是回归测试。

## 3. 已确定的技术决策

| 决策项 | 选择 |
|---|---|
| Agent 类型 | 单 Agent、有限状态工作流 |
| 编排方式 | 代码定义状态图，不要求首期引入 Agent 框架 |
| 产品形态 | 对话式测试 Agent + 结构化 Artifact 工作区 |
| LLM 接入 | Anthropic Adapter + OpenAI-compatible Adapter，保留旧包装器 |
| 工具 | 白名单领域工具，Pydantic 输入/输出 |
| 输出 | JSON Schema/Pydantic；不再依赖自由文本正则 |
| 任务执行 | MySQL 持久化任务 + 单 Worker；前端轮询 |
| 数据库变更 | Alembic migration |
| 人工边界 | 保存用例、主动探测、重新执行必须审批 |
| 评测 | 结果、工具、轨迹、安全、稳定性、延迟和成本 |
| 发布 | legacy/agent 双链路影子对比，支持快速回滚 |

## 4. 目标架构

```text
React Agent Workspace
  → 对话 / GATE / Artifact / 审批
  → Session API：消息 / 事件 / Skill / Run / Artifact
  → MySQL：sessions / messages / events / runs / steps / artifacts
  → Agent Worker
      → Skill Router / Skill Registry
      → Workflow Registry
      → Bounded Agent Runner
      → LLM Gateway
      → Tool Registry
      → Deterministic Validators
      → 现有业务 Service 和数据表
```

### 4.1 公共组件职责

#### LLM Gateway

- 根据 scene_code 获取 Provider 和 Model。
- 支持 system/user 多消息。
- 支持结构化输出能力标记和兼容降级。
- 统一超时、429/5xx 有界重试、错误分类和 usage 采集。
- 返回内容、模型、Provider、token、耗时、request_id 和 finish_reason。
- 保留现有调用函数作为兼容入口。

#### Agent Runner

- 管理状态、步骤、预算、取消、heartbeat 和终止条件。
- 每个步骤使用独立短事务，不跨 LLM 调用持有数据库事务。
- 状态至少包含：queued/running/waiting_approval/succeeded/failed/cancelled/interrupted。

#### Tool Registry

每个工具必须声明：

- 名称和用途；
- Pydantic 输入/输出；
- read/write；
- 所需权限；
- 是否幂等；
- 是否需要审批；
- 最大返回大小和超时。

#### Guardrails

- 项目权限；
- Prompt Injection 隔离；
- Authorization、Cookie、Token、password、secret、API Key 脱敏；
- 上下文长度治理；
- 结构化输出校验；
- 工具和模型调用预算；
- 写操作审批。

## 5. V2.1：用例生成 Agent

### 5.1 版本目标

先建立最小对话式测试 Agent Shell，再把“需求生成功能用例”和“接口文档生成接口用例”实现为第一个 `case_generation` Skill，同时保留两个 V1 生成接口作为 baseline 和回滚路径。

### 5.2 用户流程

```text
用户在 Agent 工作台描述目标，或从需求/接口文档点击“交给 Agent”
  → 创建或恢复 Session，并选择 case_generation Skill
  → 确认来源和范围 [GATE]
  → Agent 读取来源、项目、模块和已有用例
  → 拆解原子条款
  → 规划覆盖维度
  → 用户确认覆盖计划 [GATE]
  → 生成候选用例
  → 本地校验、去重、计算覆盖矩阵
  → 发现缺口后定向修正，最多 2 轮
  → waiting_approval
  → 对话区展示进度，Artifact 区展示覆盖证据
  → 用户勾选并批准保存 [GATE]
```

### 5.3 状态与资源上限

```text
INIT
→ LOAD_CONTEXT
→ DECOMPOSE_SOURCE
→ PLAN_COVERAGE
→ GENERATE_CANDIDATES
→ LOCAL_VALIDATE
→ REVIEW_COVERAGE
→ REPAIR_GAPS（最多 2 轮）
→ WAITING_APPROVAL
→ SAVE_SELECTED / CANCELLED
```

- 模型调用最多 4 次。
- 修正最多 2 轮。
- 达到覆盖停止条件后立即结束生成。
- 未经审批保存数量必须为 0。

### 5.4 工具白名单

- `load_source_context`
- `load_project_module_context`
- `list_existing_cases`
- `list_related_api_documents`
- `validate_case_schema`
- `validate_case_business_rules`
- `deduplicate_cases`
- `compute_coverage_matrix`
- `dry_run_api_case_codegen`

`dry_run_api_case_codegen` 只能在内存中调用现有规则方法检查候选是否可生成合法 pytest；禁止落库、写文件和发送真实请求。

### 5.5 中间产物合同

```json
{
  "source": {"type": "requirement", "id": 1},
  "atomic_clauses": [
    {"clause_id": "REQ-001", "text": "...", "priority": "P1"}
  ],
  "assumptions": [],
  "coverage_plan": [],
  "candidates": [
    {
      "candidate_id": "CASE-001",
      "payload": {},
      "covered_clause_ids": ["REQ-001"],
      "validation_errors": [],
      "revision": 1
    }
  ],
  "coverage_matrix": {},
  "warnings": []
}
```

未知的接口、字段、参数和业务规则必须进入 `assumptions`，不得静默当作事实。

### 5.6 API 合同

- `POST /agent-runs/case-generation`
- `GET /agent-runs/{run_id}`
- `GET /agent-runs/{run_id}/steps`
- `POST /agent-runs/{run_id}/cancel`
- `POST /agent-runs/{run_id}/refine`
- `POST /agent-runs/{run_id}/save-candidates`

保存接口只接收 `candidate_id[]`。后端从 Agent 输出中重新读取候选，校验来源、权限、candidate hash 和运行状态，不信任前端提交的完整 payload。

### 5.7 任务拆分

#### V2.1-T01：冻结 V1 Baseline

目标：为两条现有生成链路建立可重复测试，后续能够做 legacy/agent 对比。

主要文件：

- 新增 `backend/tests/services/test_function_case_generation_service.py`
- 新增 `backend/tests/services/test_api_document_generation_service.py`
- 新增 `backend/tests/fixtures/`
- 必要时小范围重构现有生成服务以注入 fake LLM

验收：

- 不调用真实模型即可覆盖成功、非法 JSON、字段缺失、权限和保存流程。
- V1 接口响应 Schema 不变化。
- 记录 baseline 样本，不预设虚假的质量提升数字。

#### V2.1-T02：引入迁移与 Agent 平台数据模型

目标：建立可回滚的数据库变更基础。

主要文件：

- 新增 `alembic.ini`
- 新增 `backend/alembic/`
- 新增 AgentSession、AgentMessage、AgentEvent、AgentRun、AgentStep、AgentArtifact、AgentApproval 模型
- 修改 `backend/app/models/__init__.py`

首期字段以 `docs/V2/03_ACCEPTANCE_CHECKLIST.md` 和真实查询需求为准，不增加没有消费者的字段。

验收：

- 空数据库可 upgrade 到最新版本。
- 现有数据库可 stamp/upgrade，不丢失 V1 数据。
- downgrade 能删除本任务新增结构，不影响 V1 表。

#### V2.1-T03：统一 LLM Gateway 与 Provider Adapter

目标：在保持旧函数兼容的前提下增加结构化调用和可观测元数据。

主要文件：

- 修改 `backend/app/services/llm_client_service.py`
- 必要时新增 `backend/app/services/llm_gateway.py`
- 新增 `backend/app/agents/providers/anthropic_adapter.py`
- 新增 `backend/app/agents/providers/openai_compatible_adapter.py`
- 修改 `backend/app/models/llm_model.py` 和对应 Schema/迁移
- 新增 `backend/tests/services/test_llm_gateway.py`

验收：

- 旧生成链路仍可调用。
- 配置错误、超时、Provider HTTP 错误和输出校验错误类型可区分。
- 429/5xx 只做有界重试，非重试错误不回退或重复调用。
- 测试不输出真实 API Key。

#### V2.1-T04：实现对话 Agent Runtime、Skill Registry 与 Worker

目标：实现 Session、Message、Event、Skill Router、Skill/Tool Registry、Artifact、Approval 和固定工作流所需的最小运行时，不实现具体业务 Skill。

为控制单次改动规模，分成两个连续子任务：

- `V2.1-T04A`：Runtime 合同、状态转换、Skill/Tool Registry、平台 Service 和 Fake Workflow 测试。
- `V2.1-T04B`：Worker 原子抢占、heartbeat、取消检查和中断恢复。

主要文件：

- 新增 `backend/app/agents/runtime.py`
- 新增 `backend/app/agents/state.py`
- 新增 `backend/app/agents/registry.py`
- 新增 `backend/app/agents/platform/`
- 新增 `backend/app/agents/tools/base.py`
- 新增 `backend/app/workers/agent_worker.py`
- 新增 `backend/app/services/agent_run_service.py`
- 新增运行时测试

验收：

- fake Skill 可以通过一条用户消息启动，并产生 Session、Event 和 Artifact。
- fake workflow 可以 queued → running → succeeded。
- 支持 failed、cancelled、interrupted 和 heartbeat 超时恢复。
- 同一任务不会被两个 Worker 重复执行。
- 最大步骤和总超时生效。

#### V2.1-T05：实现用例生成工具

目标：把数据库读取和确定性校验封装为带权限的纯领域工具。

主要文件：

- 新增 `backend/app/agents/tools/case_context_tools.py`
- 新增 `backend/app/agents/tools/case_validation_tools.py`
- 新增 `backend/app/agents/validators/case_validators.py`
- 复用现有 Service，不把 SQL 写进 Agent Prompt
- 新增权限、去重、覆盖和 dry-run 测试

验收：

- 每个工具都有 Pydantic 输入/输出。
- 跨项目读取被拒绝。
- dry-run 不写数据库、不写测试文件、不发请求。
- 覆盖矩阵由确定性代码计算。

#### V2.1-T06：实现用例生成 Skill 与 Workflow

前置门禁：`V2.1-T05.1` 必须修复 API `method+url` 过度去重和已有功能用例字段别名不一致问题，并完成回归后才能开始本任务。

目标：实现 5.3 的状态图和有限修正循环。

主要文件：

- 新增 `backend/app/agents/workflows/case_generation.py`
- 新增 `backend/app/agents/skills/case_generation/skill.yaml`
- 新增 `backend/app/agents/skills/case_generation/instructions.md`
- 新增 `backend/app/agents/prompts/case_generation/`
- 新增 Workflow 单元测试和集成测试

验收：

- requirement 和 api_document 两种来源均支持。
- Skill 可由显式 skill_code 或对话路由启动。
- 范围确认和覆盖计划确认形成可恢复 GATE。
- 非法模型输出进入一次结构化修正，不无限重试。
- 只修正缺口和非法候选，不全量重生成。
- 候选具有 clause trace、assumptions、validation_errors 和 revision。

#### V2.1-T07：实现会话、消息、Artifact API 和保存审批

目标：暴露 Session、Message、Event、Skill Run、Artifact、取消、修正和保存审批接口。

主要文件：

- 新增 `backend/app/schemas/agent.py`
- 新增 `backend/app/routers/agent_router.py`
- 修改 `backend/app/main.py`
- 新增 API 集成测试

验收：

- 创建接口立即返回 202 和 run_id。
- Session 消息可以启动或继续一个 Skill Run。
- GATE 可以批准、修改或暂停。
- Artifact 与 Session/Run 关联并可恢复查看。
- 查询和步骤接口执行项目权限校验。
- 重复保存幂等。
- 未处于 waiting_approval 的任务不能保存。
- V1 生成和保存接口仍可使用。

#### V2.1-T08：接入 Agent 对话工作台与结构化 Artifact

目标：新增统一 Agent 工作台，在需求页和接口文档页增加“交给 Agent”，实现对话、GATE、进度、Artifact、覆盖矩阵和人工保存。

主要文件：

- 新增 `frontend/src/api/agent.js`
- 新增 `frontend/src/pages/AgentWorkspacePage.jsx`
- 新增 `frontend/src/components/AgentConversation.jsx`
- 新增 `frontend/src/components/AgentGateCard.jsx`
- 新增 `frontend/src/components/AgentArtifactPanel.jsx`
- 新增 `frontend/src/components/AgentRunTimeline.jsx`
- 新增 `frontend/src/components/CoverageMatrix.jsx`
- 修改 `frontend/src/pages/RequirementPage.jsx`
- 修改 `frontend/src/pages/ApiDocPage.jsx`

验收：

- 任务进行中可轮询并取消。
- 用户可在当前会话通过自然语言启动和局部修正。
- 范围与覆盖计划需要明确确认。
- 页面展示步骤、候选、覆盖、假设和警告。
- 用户可勾选候选保存。
- 旧生成入口可通过 feature flag 保留。
- `npm run build` 通过。

#### V2.1-T09：影子评测与版本验收

目标：用固定样本对比 legacy 和 Agent，确认是否可以切换默认入口。

主要文件：

- 新增 `backend/tests/evals/case_generation/`
- 更新 `docs/V2/02_DEVELOPMENT_RECORD.md`
- 更新 `docs/V2/03_ACCEPTANCE_CHECKLIST.md`

验收：

- Schema、权限、脱敏、审批和资源上限硬门禁全部通过。
- 输出覆盖率、重复率、幻觉率、专家接受率、延迟和 token 的真实 baseline/agent 对比。
- 未达到门禁时保持 legacy 默认，不通过改文案掩盖问题。

### 5.8 V2.1 完成定义

V2.1 只有同时满足以下条件才完成：

- V2.1-T01 至 T09 全部有真实验证证据。
- 用户可以通过对话或“交给 Agent”启动 case_generation Skill。
- 需求和接口文档均可通过 Agent 生成候选。
- Agent 会读取上下文、调用确定性工具并针对缺口有限修正。
- 所有候选在用户审批前不会写入业务用例表。
- legacy 接口仍可回滚。
- V1 核心回归通过。

## 6. V2.2：测试失败根因分析 Agent

### 6.1 版本目标

把自由文本失败分析升级为基于冻结执行证据、确定性预诊断、历史对比和证据验证的根因分析 Agent。

### 6.2 硬前置

V2.2 不得直接从 Prompt 改造开始，必须先让执行记录能够复现当时的证据：

- 用例定义快照和 hash；
- 实际执行代码快照和 code hash；
- 参数替换后的实际请求摘要；
- Python、pytest、runner/parser version；
- subprocess exit code、timeout 和 duration；
- 场景失败步骤与上游步骤关系。

### 6.3 状态与资源上限

```text
INIT
→ AUTHORIZE_AND_FREEZE_CONTEXT
→ REDACT_ARTIFACTS
→ DETERMINISTIC_PRE_DIAGNOSIS
→ BUILD_HYPOTHESES
→ SELECT_READ_ONLY_TOOLS
→ VERIFY_EVIDENCE
→ FETCH_ONE_MORE_EVIDENCE_ROUND（最多 1 轮）
→ SYNTHESIZE_RESULT
→ CONFIDENCE_GATE
→ DONE / INCONCLUSIVE
```

- 模型调用最多 2 次。
- 工具调用最多 6 次。
- 额外取证最多 1 轮。
- 默认无主动重跑工具。

### 6.4 只读工具白名单

- `load_run_snapshot`
- `load_case_definition`
- `parse_pytest_failure`
- `audit_generated_code`
- `compare_case_history`
- `load_scene_trace`
- `lookup_api_contract`
- `check_environment_evidence`
- `redact_artifact`

### 6.5 输出合同

```json
{
  "target": {"type": "test_run", "id": 123},
  "diagnosis_status": "confirmed | likely | inconclusive",
  "primary_cause": {
    "category": "assertion",
    "subtype": "brittle_exact_match",
    "summary": "...",
    "confidence": 0.88
  },
  "hypotheses": [],
  "evidence": [
    {
      "evidence_id": "EV-001",
      "source_type": "test_run",
      "source_id": 123,
      "path": "parsed_failure.actual",
      "excerpt": "...",
      "supports": true
    }
  ],
  "recommendations": [],
  "missing_evidence": [],
  "risk_level": "low | medium | high"
}
```

`confidence` 表示诊断可信度，`risk_level` 表示影响严重度。证据不足时必须允许 `inconclusive`。

### 6.6 任务拆分

#### V2.2-T01：冻结单用例执行证据

主要文件：

- 修改 `backend/app/models/test_run.py`
- 修改 `backend/app/services/run_service.py`
- 修改 `backend/app/utils/pytest_runner.py`
- 新增迁移和执行快照测试

验收：旧运行分析不再依赖修改后的当前用例和代码；pytest subprocess 有 timeout；快照敏感字段有脱敏策略。

#### V2.2-T02：实现确定性证据解析工具

主要文件：

- 新增 `backend/app/agents/tools/rca_context_tools.py`
- 新增 `backend/app/agents/tools/rca_diagnostic_tools.py`
- 新增 `backend/app/agents/validators/evidence_validators.py`
- 新增典型失败 fixture 和测试

验收：SyntaxError、ImportError、NameError、断言差异、401/403、参数错误、5xx、DNS/timeout 可被结构化提取；工具不执行代码、不访问任意 URL。

#### V2.2-T03：实现根因分析 Workflow

主要文件：

- 新增 `backend/app/agents/workflows/failure_rca.py`
- 新增 `backend/app/agents/prompts/failure_rca/`
- 新增 Workflow 测试

验收：每个事实性结论必须绑定可解析 evidence_id；缺证据样本输出 inconclusive；无证据高置信结论被 Validator 拒绝。

#### V2.2-T04：实现根因分析 API 与兼容层

主要文件：

- 扩展 `backend/app/routers/agent_router.py`
- 修改 `backend/app/services/analysis_service.py` 为兼容 façade 或保留 legacy feature flag
- 扩展 `backend/app/models/ai_analysis.py` 和迁移
- 新增 API 测试

验收：查看已有分析与重新分析分离；同一 context hash 不重复创建活跃任务；旧 GET/POST 行为有明确兼容策略。

#### V2.2-T05：接入单用例失败分析前端

主要文件：

- 新增 `frontend/src/components/RootCauseEvidence.jsx`
- 修改 `frontend/src/pages/RunPage.jsx`
- 修改 `frontend/src/pages/CasePage.jsx`

验收：展示状态、根因、置信度、风险、证据、备选假设、缺失证据和建议；不再用正则解析自由文本；`npm run build` 通过。

#### V2.2-T06：扩展场景失败分析

主要文件：

- 扩展 RCA context tools
- 修改 `frontend/src/pages/ScenePage.jsx` 或 `SceneStepPage.jsx`
- 新增 SceneRun/SceneStepRun 集成测试

验收：失败步骤可以引用上游变量、提取结果和断言证据；上游失败与当前步骤失败可区分。

#### V2.2-T07：根因评测与灰度切换

主要文件：

- 新增 `backend/tests/evals/failure_rca/`
- 更新 V2 开发记录和验收清单

验收：输出主分类、细分类、证据正确率、inconclusive 识别、稳定性、延迟和 token 的真实结果；安全硬门禁通过后才允许切换默认入口。

### 6.7 V2.2 完成定义

- V2.2-T01 至 T07 全部有真实证据。
- TestRun 和 SceneStepRun 均可分析。
- 旧运行使用冻结证据，不读取变化后的当前代码冒充运行代码。
- 每个根因都有证据引用，证据不足可返回 inconclusive。
- 默认没有自动重跑和任意网络探测。
- legacy 失败分析可回滚。

## 7. V2.3：测试 Skill 扩展与细节优化

V2.3 在优化 V2.1/V2.2 的质量、可靠性和使用体验基础上，增加测试数据准备和缺陷描述两个 Skill。写环境数据的高风险工具必须单独验收。

### V2.3-T01：安全加固

- Prompt Injection 测试集
- 敏感字段递归脱敏
- 工具权限和跨项目越权测试
- 审批动作幂等与审计
- LLM API Key 存储方案评估

### V2.3-T02：可观测性与成本

- 统一结构化日志
- run_id、step_id、project_id、user_id 关联
- token、延迟、错误码和重试统计
- 卡死任务和 heartbeat 恢复
- 慢工具和高成本运行查询

### V2.3-T03：前端交互

- Agent 进度和取消体验
- 覆盖矩阵和根因证据可读性
- 历史运行、模型和 Prompt 版本展示
- 失败重试和错误提示
- legacy/agent 对比入口

### V2.3-T04：评测与回归工程

- 固定离线样本版本
- 确定性 grader
- 可观察轨迹约束
- 重复运行稳定性
- CI 中执行安全硬门禁和 V1 回归

### V2.3-T05：性能与数据治理

- 上下文裁剪和重复内容消除
- AgentStep 大字段归档策略
- 数据保留与删除关联
- 索引、分页和查询性能
- 迁移、备份和恢复演练

### V2.3-T06：测试数据准备 Skill

- 优先检索和复用已有测试数据或工具
- 首期先实现只读查询、方案预览和工具选择
- 写操作限定测试环境并使用 Approval
- 参数 Schema、幂等键、回滚/清理说明和审计事件
- 不允许模型生成任意 SQL 后直接执行

### V2.3-T07：缺陷描述生成 Skill

- 从用户描述、失败运行、请求响应、日志和附件读取证据
- 生成结构化 defect_draft Artifact
- 输出标题、环境、前置、步骤、实际、预期、影响和证据引用
- 用户编辑和确认后才能复制或提交缺陷系统
- 信息不足时列出待确认字段，不编造复现条件

### V2.3 完成定义

- V2.1、V2.2 的安全硬门禁进入自动化测试。
- 测试数据准备和缺陷描述 Skill 通过独立权限与 Artifact 验收。
- Agent 运行有完整可观察轨迹和成本统计。
- 关键页面可用性经过人工验收。
- V1、V2.1、V2.2 回归均通过。
- 开发记录和实际系统状态一致。

## 8. V2.4：待定

V2.4 不在当前实施范围内。

只有完成 V2.1–V2.3 并获得真实运行数据后，用户与 Codex 才决定是否选择以下方向之一：

- 受控重跑和验证动作；
- 报告 Agent；
- 场景生成 Agent；
- 检索增强；
- 更可靠的分布式任务队列；
- 对外集成或插件能力。

Claude Code 不得提前为 V2.4 新增表、接口、抽象层或依赖。

## 9. 跨版本验收门禁

### 硬门禁

- JSON/Pydantic 输出合法。
- 未授权跨项目访问数为 0。
- secret 出站泄漏数为 0。
- 未审批自动保存/重跑数为 0。
- 不超过最大步骤、工具和模型调用预算。
- 所有数据库迁移可升级、可回滚。
- V1 核心链路仍可用。

### 质量指标

质量指标先测 legacy baseline，再锁定 V2 阈值，不预先编造目标：

- 用例条款覆盖率、重复率、幻觉率、专家接受率；
- 根因分类、证据正确率、inconclusive 识别、专家可采信性；
- 重复运行稳定性；
- p50/p95 延迟、token 和模型调用成本。

## 10. Claude Code 任务提示词模板

用户与 Codex 每次只把一个任务编号交给 Claude Code：

```text
请执行 TestMind 任务：<任务编号，例如 V2.1-T01>。

开始前必须阅读：
1. docs/PROJECT_RECORD.md
2. docs/V2/01_AGENT_DEVELOPMENT_PLAN.md
3. docs/V2/06_TEST_AGENT_PLATFORM_ARCHITECTURE.md
4. docs/V2/04_CASE_GENERATION_AGENT_PRD.md（V2.1 任务）
5. docs/V2/05_CASE_GENERATION_AGENT_TECHNICAL_DESIGN.md（V2.1 任务）
6. docs/V2/02_DEVELOPMENT_RECORD.md
7. docs/V2/03_ACCEPTANCE_CHECKLIST.md

严格要求：
- 只完成该任务，不提前实现后续任务或版本。
- 先只读核验真实源码和 git status。
- 修改前先输出目标、事实判断、完整文件清单、验证命令、风险与回滚方式。
- 保留用户已有修改，不覆盖无关文件。
- 实现后运行计划书规定的测试和受影响的 V1 回归。
- 把实际命令、真实结果、问题和修改文件写入 V2 开发记录。
- 没有证据不得标记完成，不得编造指标。

现在完成源码核验，输出简短实施摘要；若未触发停止条件，直接编码、验证并更新开发记录，不等待二次确认。
```

