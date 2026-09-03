# TestMind V2 开发记录

> 最后更新：2026-09-03
>
> 本文件只记录真实实施结果和证据。计划内容写入 `01_AGENT_DEVELOPMENT_PLAN.md`，未执行的任务不得写成已完成。

## 1. 当前状态

| 版本 | 状态 | 当前任务 | 说明 |
|---|---|---|---|
| V2.1 | 进行中 | V2.1-T08 | T01–T07 已完成；T08 悬浮工作台主闭环已隔离联调，真实环境与扩展交互待验收 |
| V2.2 | 未开始 | — | 依赖 V2.1 验收 |
| V2.3 | 未开始 | — | 测试 Skill 扩展与细节优化，依赖 V2.1、V2.2 验收 |
| V2.4 | 待定 | — | 不在当前范围 |

## 2. V2.1 任务状态

| 任务 | 内容 | 状态 | 完成日期 | 证据 |
|---|---|---|---|---|
| V2.1-T01 | 冻结 V1 用例生成 Baseline | 已完成 | 2026-09-01 | 33 个 baseline 测试通过，见下方任务记录 |
| V2.1-T02 | 引入迁移与 Agent 平台数据模型 | 已完成 | 2026-09-01 | Alembic 增量接管 + 7 张 Agent 表，50 个测试通过，见下方任务记录 |
| V2.1-T03 | LLM Gateway 与 Provider Adapter | 已完成 | 2026-09-02 | 102 个测试通过（50 既有 + 52 新增），见下方任务记录 |
| V2.1-T04 | 对话 Runtime、Skill Registry 与 Worker | 已完成 | 2026-09-02 | T04A Runtime 核心/Registry/Service + T04B Worker/抢占/heartbeat/中断恢复，191 个测试通过 |
| V2.1-T05 | 用例生成领域工具 | 已完成 | 2026-09-02 | 9 个只读工具 + 确定性校验器，230 个测试通过，见下方任务记录 |
| V2.1-T06 | 用例生成 Skill 与 Workflow | 已完成 | 2026-09-02 | 三 GATE 受控流程 + 修正循环 + 双 Artifact，288 个测试通过，见下方任务记录 |
| V2.1-T07 | 会话、消息、Artifact API 与保存审批 | 已完成 | 2026-09-02 | 14 个 API 端点 + 保存事务与幂等，316 个测试通过，见下方任务记录 |
| V2.1-T08 | Agent 对话工作台与结构化 Artifact | 主闭环完成，扩展项待定 | 2026-09-03 | 6 条前端合同测试、2 条针对性 API 测试、浏览器隔离联调；见第 18 节及 09 联调文档 |
| V2.1-T08.1 | 修复正式环境 Agent 创建会话 500（项目/来源校验前置化 + 前端可操作报错） | 已完成 | 2026-09-03 | 新增 11 条 API + 6 条 Service 针对性测试；隔离库开启 SQLite 外键；见第 19 节 |
| V2.1-T09 | 影子评测与版本验收 | 待开发 | — | — |

## 3. V2.2 任务状态

| 任务 | 内容 | 状态 | 完成日期 | 证据 |
|---|---|---|---|---|
| V2.2-T01 | 冻结单用例执行证据 | 未开始 | — | — |
| V2.2-T02 | 确定性证据解析工具 | 未开始 | — | — |
| V2.2-T03 | 根因分析 Workflow | 未开始 | — | — |
| V2.2-T04 | 根因分析 API 与兼容层 | 未开始 | — | — |
| V2.2-T05 | 单用例失败分析前端 | 未开始 | — | — |
| V2.2-T06 | 场景失败分析 | 未开始 | — | — |
| V2.2-T07 | 根因评测与灰度切换 | 未开始 | — | — |

## 4. V2.3 任务状态

| 任务 | 内容 | 状态 | 完成日期 | 证据 |
|---|---|---|---|---|
| V2.3-T01 | 安全加固 | 未开始 | — | — |
| V2.3-T02 | 可观测性与成本 | 未开始 | — | — |
| V2.3-T03 | 前端交互优化 | 未开始 | — | — |
| V2.3-T04 | 评测与回归工程 | 未开始 | — | — |
| V2.3-T05 | 性能与数据治理 | 未开始 | — | — |
| V2.3-T06 | 测试数据准备 Skill | 未开始 | — | — |
| V2.3-T07 | 缺陷描述生成 Skill | 未开始 | — | — |

## 5. 已确认技术决策

| 日期 | 决策 | 原因 | 状态 |
|---|---|---|---|
| 2026-09-01 | V2.1 先做用例生成 Agent | 现有预览与人工保存边界完整，改造风险较低 | 生效 |
| 2026-09-01 | V2.2 再做根因分析 Agent | 必须先补冻结证据，技术依赖更多 | 生效 |
| 2026-09-01 | 首期使用受控单 Agent | 避免多 Agent 和框架堆叠 | 生效 |
| 2026-09-01 | 保留 legacy 链路做影子对比 | 支持 baseline、回归和快速回滚 | 生效 |
| 2026-09-01 | V2.4 暂不设计 | 等待 V2.1–V2.3 真实数据 | 生效 |
| 2026-09-01 | V2.1 使用任务式 UI，不以聊天页为主入口 | 已被后续“对话控制面 + Artifact 工作区”决策替代 | 已替代 |
| 2026-09-01 | V2.1 首期不用通用 Agent 框架 | 固定流程可用 Python 状态机实现，降低学习和集成成本 | 生效 |
| 2026-09-01 | TestMind 自建测试专用 Agent，不启动 Claude Code CLI | 保持产品权限、模型适配和业务 Artifact 的自主控制 | 生效 |
| 2026-09-01 | V2.1 使用对话控制面 + 结构化 Artifact 工作区 | 同时保留自然交互、GATE、覆盖矩阵和批量保存能力 | 生效 |
| 2026-09-01 | Claude 作为 Provider Adapter 接入 | 可复用 Claude 能力，但不把核心 Runtime 绑定单一模型 | 生效 |

## 6. 风险与阻塞项

| 编号 | 问题 | 影响 | 当前处理 | 状态 |
|---|---|---|---|---|
| R-001 | 项目当前没有正式数据库迁移链路 | Agent 表和旧表字段无法可靠升级 | V2.1-T02 已引入 Alembic（增量接管），V1 全量 schema migration 仍缺 | 处理中 |
| R-002 | 当前缺少独立平台回归测试 | Agent 改造可能破坏 V1 | V2.1-T01 已建立用例生成链路 baseline，其余 V1 回归仍缺 | 待处理 |
| R-003 | 失败运行没有完整冻结快照 | 旧失败可能读取新代码后误归因 | V2.2-T01 先补证据 | 待处理 |
| R-004 | 工作区可能存在用户未提交修改 | 实施时存在覆盖风险 | 每个任务先检查 git status | 持续关注 |

## 7. 单任务记录模板

Claude Code 每完成一个任务，在本文件末尾追加一节，不覆盖旧记录：

````markdown
## YYYY-MM-DD — <任务编号> <任务名称>

### 状态

已完成 / 部分完成 / 阻塞 / 失败

### 目标

本次实际完成的范围。

### 源码核验

- 修改前确认的关键事实和对应文件。

### 修改文件

- `path/to/file`：实际改动。

### 数据库迁移

- migration id、upgrade/downgrade 结果；无则写“无”。

### 验证命令与真实结果

```text
命令：...
结果：passed/failed，测试数量或关键输出。
```

### V1 回归

- 实际执行的回归项和结果。

### 遗留问题

- 没有则写“无”。

### 下一步

- 只能指向主计划中的后续任务，不直接开始实施。
````

## 8. 文档结构调整记录

### 2026-09-01 — V2 规划文档初始化

状态：已完成文档规划，未实施代码。

完成内容：

- 将项目文档拆分为总项目记录、V1 历史资料和 V2 执行资料。
- 确定 V2.1、V2.2、V2.3、V2.4 的版本边界。
- 建立 Claude Code 可执行的任务编号、验收和记录格式。
- 建立 V2.1 用例生成 Agent PRD 和持续更新的技术设计学习文档。
- 基于实习项目关键模式，建立 TestMind 对话式测试 Agent 平台架构文档。

验证：仅文档结构检查，不代表任何 V2 功能已完成。

## 9. 2026-09-01 — V2.1-T01 冻结 V1 用例生成 Baseline

### 状态

已完成

### 目标

为 V1 两条 one-shot 用例生成链路（需求→功能用例、接口文档→接口用例）建立不依赖真实 LLM、不连接真实 MySQL 的可重复 Baseline 测试，冻结生成、解析、校验、预览、保存与权限的当前行为，供后续 legacy/agent 对比与回归使用。

### 源码核验

- 功能用例链：`backend/app/services/function_case_generation_service.py`；场景编码 `requirement_to_function_case`；解析复用接口用例多策略解析器（`parse_llm_api_cases`）；校验要求 case_name/steps_json/expected_result 非空；保存时 project_id 以后端 RequirementDoc 为准、source="llm"。
- 接口用例链：`backend/app/services/api_document_generation_service.py`；场景编码 `api_doc_to_api_case`；`call_llm_by_scene` 存在 .env 回退；保存 headers/body/expected_result 为 JSON 字符串。
- 权限：`backend/app/services/permission_service.py`；写 = 角色门禁 + can_operate；viewer 即使有项目权限记录也不能执行写操作。
- 测试基础设施：此前仓库无 conftest/pytest.ini；`backend/requirements.txt` 已含 pytest==8.3.3；`backend/tests/` 目录存在但为空。
- `app/core/database.py` 有 SQLite 分支，`ensure_mysql_database_exists` 对非 MySQL 直接返回；pydantic-settings 环境变量优先于 .env，可在导入 app 前覆盖 DATABASE_URL。

### 修改文件

- 新增 `backend/tests/conftest.py`：导入 app 前强制覆盖 DATABASE_URL=sqlite:///:memory: 与 LLM 环境变量（mock、空 Key），杜绝真实 MySQL、真实 LLM、真实 API Key 与网络；`db_session` fixture 每条测试 drop_all/create_all 全量重建，测试互不依赖。
- 新增 `backend/tests/fixtures/function_cases_valid.json`：虚构登录需求的 Fake LLM 输出，含一条完整字段用例与一条 steps/test_data 别名用例。
- 新增 `backend/tests/fixtures/api_cases_valid.json`：虚构登录接口的 Fake LLM 输出，method/priority 为小写以冻结规范化行为。
- 新增 `backend/tests/services/test_function_case_generation_service.py`：11 条测试。
- 新增 `backend/tests/services/test_api_document_generation_service.py`：15 条测试。
- 新增 `backend/tests/services/test_generation_permissions.py`：7 条测试。
- 修改 `docs/V2/03_ACCEPTANCE_CHECKLIST.md`：勾选 3.1 第一条。
- 修改 `docs/V2/08_LEARNING_BACKLOG.md`：T01 知识点更新为已实践。

未修改任何业务代码；未修改 requirements.txt；未新增 pytest.ini。

### 数据库迁移

无。

### 验证命令与真实结果

```text
命令（backend 目录）：
  export DATABASE_URL="sqlite:///:memory:" && export LLM_PROVIDER="mock" && export LLM_API_KEY=""
  python -m pytest tests/services/test_function_case_generation_service.py tests/services/test_api_document_generation_service.py tests/services/test_generation_permissions.py -q
结果：首轮 30 passed, 2 failed（2 个失败均为测试自身断言错误，修正测试后通过）

  python -m pytest tests -q
结果：33 passed, 14 warnings in 1.31s
（14 个 warnings 为既有 pydantic/starlette 弃用提示，与新增测试无关）

  git diff --check
结果：exit 0（仅有 README.md 的 LF→CRLF 提示，非本任务文件）
```

### V1 回归

- 本任务为新增测试，未改动任何 V1 业务代码，不存在受影响的 V1 回归项。

### 发现的问题（Baseline 冻结的当前事实）

1. 接口用例保存不规范化 priority/case_type：生成时校验并回退非法值，保存时原样入库（`test_save_priority_and_case_type_stored_as_is` 冻结）。疑似缺陷，登记为独立问题，不在本任务修复。
2. api_cases 表无 remark 列，`GeneratedApiCaseItem.remark` 在保存时被静默丢弃。
3. 功能用例生成链路解析器复用接口用例的多策略解析器，并保留 steps/test_data/case_name←name 别名回退。
4. 接口文档 Prompt 中 content 优先于 name（`content or name`）；content 非空时 name 不进入 Prompt。
5. 保存接口中前端 module_id 优先于后端文档/需求的 module_id（project_id 以后端为准，module_id 信任前端）。
6. 功能用例 `generate_count` 参数不进入 Prompt（Prompt 固定"最多 50 条"）。
7. `call_llm_by_scene` 在场景未配置时会回退 .env 直连 LLM；测试环境通过 conftest 强制 mock 环境变量封死该回退。

### 遗留问题

- Router 级 API 集成测试（TestClient + token 管道）不在本任务范围；permission_service 确定性规则已测，Router 集成测试待后续任务补充。

### 下一步

- 按主计划执行 V2.1-T02（Alembic 与 Agent 平台数据模型），本任务停止于此。

## 10. 2026-09-01 — V2.1-T02 引入迁移与 Agent 平台数据模型

### 状态

已完成

### 目标

引入 Alembic 以增量接管现有 create_all 管理的 V1 schema；创建七张 Agent 平台表（Session/Message/Event/Run/Step/Artifact/Approval）与集中 Schema/常量；只做数据层，不实现 Runtime、LLM Gateway、Skill、Tool、API 或前端；全部验证在临时 SQLite 上完成。

### 源码核验

- V1 的 21 张表由 main.py 的 `Base.metadata.create_all()` 维护，仓库无任何 Alembic 配置与历史 revision。
- 生产库 MySQL；测试用 SQLite（conftest 在导入 app 前强制覆盖 DATABASE_URL）。
- 现有模型惯例：Integer 自增 PK 且带 index=True（create_all 会为 PK 列生成 `ix_<table>_id` 索引）、String status + 注释枚举、JSON 大字段、DateTime(timezone=True) + server_default func.now()、无 relationship；FK 使用不一致（部分表用裸 Integer 归属字段）。
- 本机未安装 Alembic；经用户授权后使用项目 venv 安装 `alembic==1.19.1`（连带 Mako 1.4.1）。

### 修改文件

- 新增 `backend/alembic.ini`（ASCII-only；Windows 下 configparser 用 locale 编码读取 ini，中文注释会触发 GBK 解码失败）
- 新增 `backend/alembic/env.py`（URL 解析顺序：显式传入 > settings.DATABASE_URL；MySQL 护栏 `ALEMBIC_ALLOW_MYSQL=1`；target_metadata=Base.metadata）
- 新增 `backend/alembic/script.py.mako`
- 新增 `backend/alembic/versions/0001_v1_schema_baseline.py`（no-op 基线标记）
- 新增 `backend/alembic/versions/0002_agent_platform_tables.py`（七张表；spec 驱动 create + 已存在表结构校验，不一致明确失败；downgrade 反向依赖删除）
- 新增 `backend/app/models/agent_session.py`、`agent_message.py`、`agent_event.py`、`agent_run.py`、`agent_step.py`、`agent_artifact.py`、`agent_approval.py`
- 修改 `backend/app/models/__init__.py`（追加 7 个 import 与 __all__ 条目）
- 新增 `backend/app/schemas/agent_platform.py`（状态/枚举集中常量 + 7 组 Create/Response Schema）
- 修改 `backend/requirements.txt`（追加 `alembic==1.19.1`）
- 新增 `backend/tests/models/test_agent_platform_models.py`（10 条测试）
- 新增 `backend/tests/migrations/test_agent_platform_migration.py`（7 条测试）
- 修改 `docs/V2/03_ACCEPTANCE_CHECKLIST.md`、`docs/V2/08_LEARNING_BACKLOG.md`

未修改：main.py、database.py、任何 Service/Router、V1 模型与表、T01 测试语义、前端。

### 数据库迁移

- revision：`0001_v1_schema_baseline`（no-op）、`0002_agent_platform_tables`
- 实际命令（backend 目录，临时 SQLite 文件）：
  - `python -m alembic stamp 0001_v1_schema_baseline`
  - `python -m alembic upgrade head` → `0002_agent_platform_tables (head)`
  - `python -m alembic downgrade 0001_v1_schema_baseline`
  - `python -m alembic upgrade head` → `0002_agent_platform_tables (head)`
- 现有数据库接入流程（migration-first）：先 `stamp 0001` → `upgrade head` → 之后才启动新代码。
- 新环境过渡流程：`create_all` + `alembic stamp head`，仅过渡标记。

### 实际表、索引与约束

- 七张表：agent_sessions、agent_messages、agent_events、agent_runs、agent_steps、agent_artifacts、agent_approvals。
- 唯一约束：`uq_agent_messages_session_seq(session_id, sequence_no)`、`uq_agent_events_session_seq(session_id, sequence_no)`、`uq_agent_steps_run_seq(agent_run_id, sequence_no)`、`uq_agent_runs_idempotency(session_id, workflow_code, idempotency_key)`。
- 索引：每表 `ix_<table>_id` + 各外键/状态/心跳列索引（如 ix_agent_runs_status、ix_agent_runs_heartbeat_at）。
- 外键：全部 `ondelete=RESTRICT`（会话/用户/项目不被级联删除）；Agent 表间引用（run/artifact 等）同样 RESTRICT。
- 状态默认值：session=active、run=queued、step=pending、artifact=draft、approval=pending。

### 验证命令与真实结果

```text
命令：python -m pytest tests -q
结果：50 passed, 14 warnings in 4.58s
（33 条 T01 Baseline + 10 条模型测试 + 7 条迁移测试）
迁移测试覆盖：存量库 stamp→upgrade 建表并校验列/唯一约束/索引/外键；
downgrade 只删 Agent 表且 V1 21 表保留；重复 upgrade 成功；
create_all 先建表的重叠场景 0002 结构校验通过；结构不一致明确抛错；0001 空库 no-op。

命令：git diff --check
结果：exit 0
```

### V1 回归

- T01 33 条 Baseline 全部继续通过（含在 50 passed 中）。
- 未修改任何 V1 业务代码与启动行为；main.py 的 create_all 只会额外出新建七张 agent 表（纯新增，不改动任何 V1 表）。

### Alembic 接管边界

- 0002 只管理 agent_* 七张表；V1 表仍由 create_all 维护。
- 完全接管需补 V1 全量 schema migration（21 张表 DDL 逐表比对），属于遗留项。

### 遗留问题

1. MySQL DDL 兼容性未在真实 MySQL 验证（本任务全部 SQLite），登记为后续测试环境验证项。
2. V1 全量 schema migration 缺失：空数据库无法仅靠 alembic 完整初始化 V1+V2。
3. 新环境 `create_all + stamp head` 仅为过渡标记，不等于完整 Alembic 初始化。
4. Windows 下 alembic.ini 含非 ASCII 字符会导致 configparser GBK 解码失败（ini 已保持 ASCII，记录此坑）。
5. env.py 导入 app.core.database 会触发既有 `ensure_mysql_database_exists` 副作用（app 自身行为，本任务未修改 database.py）。

### 下一步

- 按主计划执行 V2.1-T03（LLM Gateway 与 Provider Adapter），本任务停止于此。

## 11. 2026-09-02 — V2.1-T03 统一 LLM Gateway 与 Provider Adapter

### 状态

已完成

### 目标

建立与具体供应商解耦的 LLM 调用层（LLMGateway + OpenAICompatibleAdapter + AnthropicAdapter），统一消息/工具/结构化输出合同、错误分类与有限重试；保留 V1 兼容入口并修复 `call_llm_by_scene` 误回退 .env 的缺陷。不实现 Runtime、Skill、Tool 执行循环、Worker、Router 或前端。

### 源码核验

- 旧实现 [llm_client_service.py](backend/app/services/llm_client_service.py)：httpx 直连 /chat/completions，全部异常折叠为普通 ValueError；`call_llm_by_scene` 把「配置错误」与「Provider 调用错误」混在一起，调用失败时可能误回退 .env 造成二次调用。
- 前端 provider_type 可选值：`openai_compatible / deepseek / openai / qwen / custom`（当前均按 OpenAI-compatible 调用），本任务新增 `anthropic` 类型。
- API Key 明文存 `llm_providers.api_key`，列表/详情经 `mask_api_key` 脱敏返回；新异常消息不包含 Key/Authorization。
- httpx 0.27.2（MockTransport 可用）；本机无 anthropic SDK，经用户授权安装 `anthropic==1.3.0`（该版本依赖 httpx2，`messages.create` 无 temperature 参数，已核验 SDK 异常类与响应类型可离线构造）。
- LLMModel 无能力字段；本任务未加字段、无 Alembic 0003（能力三态当前无持久化消费者）。

### 修改文件

- 新增 `backend/app/exceptions/__init__.py`、`llm_errors.py`：6 类统一异常（error_code + retryable，不泄露 Secret；LLMConfigurationError 继承 ValueError 保住 V1 catch 合同）。
- 新增 `backend/app/schemas/llm_gateway.py`：LLMMessage/LLMToolSpec/LLMToolCall/LLMRequest/LLMResult 统一数据合同。
- 新增 `backend/app/agents/__init__.py`、`providers/{__init__,base,openai_compatible_adapter,anthropic_adapter}.py`。
- 新增 `backend/app/services/llm_gateway.py`。
- 修改 `backend/app/services/llm_client_service.py`：内部改造为 Gateway 薄包装；4 个旧函数签名与字符串合同不变；`call_llm_by_scene` 只在 LLMConfigurationError 时回退 .env。
- 修改 `backend/requirements.txt`：+`anthropic==1.3.0`。
- 新增 `backend/tests/providers/test_openai_compatible_adapter.py`（14 条）、`test_anthropic_adapter.py`（11 条）、`backend/tests/services/test_llm_gateway.py`（27 条）。
- 修改 `docs/V2/02/03/05/08`。

### 数据库迁移

无（不新增能力字段，无 0003）。

### 验证命令与真实结果

```text
命令：python -m pytest tests -q
结果：102 passed, 14 warnings in 8.11s（T01/T02 50 条 + 本任务 52 条）
命令：git diff --check
结果：exit 0
```

### 最终落地要点

- 能力三态 `Capability`：supported / unsupported / unknown。OpenAI-compatible 基线全 unknown（不默认附加 response_format、不对 tools 做统一假定）；Anthropic 基线 tools/streaming=supported、structured_output=unsupported；Gateway 支持 `capability_overrides` 代码映射。
- 结构化输出两级降级：原生 response_format 仅在能力 SUPPORTED 时附加；默认走「JSON 提示约束 + Pydantic 本地校验」，校验摘要只含 loc/msg/type、不含输入值（有测试断言 secret 值不出现）。
- 重试只在 Gateway：默认 max_retries=2、指数退避、sleeper 可注入；只重试 timeout/连接错误/429/5xx；400/401/403 与输出校验错误不重试；Anthropic SDK 客户端显式 max_retries=0，避免 SDK/Gateway 双重重试。
- `.env` 回退修复：`call_llm_by_scene` 只捕获 LLMConfigurationError 做回退；Provider 调用失败直接上抛（测试断言 .env 不被调用）。
- Adapter 只做请求/响应转换与 tool_calls 解析，不执行工具（测试断言只透传）。

### V1 回归

- T01/T02 50 条全部继续通过（含在 102 passed 中）。
- 两条 V1 用例生成 Service、Router、前端零改动；`get_model_config_by_scene` 消息文案不变、仍可被 `except ValueError` 捕获。

### 未支持的能力 / 遗留问题

1. Anthropic temperature 首期不转发（anthropic==1.3.0 的 messages.create 无该参数），待后续版本评估。
2. Anthropic 原生结构化输出（tool-based）未实现，首期与 OpenAI-compatible 一样走本地校验。
3. 能力三态无持久化消费方（无 LLMModel 字段、无 API），模型特例能力需经代码 override 映射；后续需要时再评估 Alembic 0003。
4. 真实供应商联调（真实 LLM / 真实 Key）不在本任务范围，Adapter 对真实 API 的响应解析未联调验证（测试用真实 SDK 类型对象与真实异常类构造，零网络）。
5. `.env` 兼容入口仍为直连 httpx（保留 V1 行为），未走 Gateway。
6. V1 前端 provider_type 别名（deepseek/openai/qwen/custom）继续映射到 OpenAI-compatible，历史行为兼容。

### 下一步

- 按主计划执行 V2.1-T04（对话 Runtime、Skill Registry 与 Worker），本任务停止于此。

## 12. 2026-09-02 — V2.1-T04A Agent Runtime 核心、Skill/Tool Registry 与平台 Service

### 状态

已完成（T04A 部分；Worker 抢占、heartbeat、中断恢复留 V2.1-T04B）

### 目标

建立测试 Skill 共用的最小 Runtime 核心（AgentRunner 同步有界本地循环）+ SkillRegistry/ToolRegistry + 四个平台数据访问 Service；用 Fake Workflow 验证闭环。不实现 Worker、真实 Skill、真实 Tool、真实 LLM、Router/API 或前端。

### 源码核验

- 七张 Agent 表字段/唯一约束/状态值（T02 已建）；`schemas/agent_platform.py` 集中常量（RUN_STATUSES/STEP_KINDS/ARTIFACT_STATUSES/APPROVAL_STATUSES）。
- LLM Gateway 公开接口 `complete(provider, model, request, response_model)`；本任务仅注入 RuntimeContext，不调用真实 LLM。
- `permission_service` 提供角色级权限；本任务 Service 采用「会话 owner 本人可见/可操作」边界，admin 绕过留 T07 Router 层。
- 无既有可复用状态转换/Service；全部新建，且无需数据库变更。

### 修改文件（全部新增 + 文档）

- `backend/app/agents/runtime/{errors,transitions,contracts,runner}.py` + `__init__.py`（保持为空，避免与 registry 的循环导入）
- `backend/app/agents/registry/{__init__,skill_registry,tool_registry}.py`
- `backend/app/services/{agent_session_service,agent_run_service,agent_artifact_service,agent_approval_service}.py`
- `backend/tests/agents/{test_skill_registry,test_tool_registry,test_runtime_transitions,test_agent_runtime}.py`
- `backend/tests/services/test_agent_platform_services.py`
- `docs/V2/{02,03,05,06,08}`

### 数据库迁移

无（不新增字段、不新增表、无 0003）。

### 验证命令与真实结果

```text
命令：python -m pytest tests -q
结果：165 passed, 14 warnings in 7.47s（102 既有 + 63 新增）
命令：git diff --check
结果：exit 0
```

### 最终接口（要点）

- `AgentWorkflow` Protocol：`initial_state / next_step / execute_step`，一次只执行一个可持久化步骤。
- `StepOutcome / RuntimeContext / WorkflowResult`（contracts.py）。
- 状态转换表（transitions.py）：`queued→running/cancelled`；`running→waiting_approval/succeeded/failed/cancelled/interrupted`；`waiting_approval→running/cancelled/failed`；`interrupted→queued/failed/cancelled`；`succeeded/failed/cancelled` 为终态。
- `AgentRunner.run(db, run)`：有界本地循环；state 持久化于 `run.output_json["workflow_state"]`；每步 commit；支持 waiting_approval 审批后从持久化 state 恢复继续执行；检查 max_steps 与 cancelled。
- Registry：code/name 唯一，重复/未知报明确错误；不动态 import、不扫描 SKILL.md。
- Service 事务边界：Service 只 add/flush 不 commit，由 Runner 每步 commit；失败先 rollback 再落 failed 记录。

### V1 / T01-T03 回归

- 102 条既有测试全部继续通过（含在 165 passed 中）。未改动任何 V1 业务、Router、main.py、database.py、前端。

### 并发与恢复边界（尚未实现）

- sequence_no 采用 max+1 生成，并发下存在竞态（T04B Worker 前单进程同步使用）。
- Runner 仅支持单进程同步测试调用，无 while True Worker、无数据库轮询、无锁。
- 原子 claim、heartbeat、中断恢复、cancelled 传播由 T04B 实现。
- 审批通过后的继续执行机制已具备（waiting_approval→running），但触发入口（API）在 T07。

### 遗留问题

1. 会话 admin 可见性/操作绕过未实现（留 T07 Router 层）。
2. sequence_no 并发安全待评估（T04B/T07）。
3. Skill/Tool 无数据库表，仅内存注册（符合 T02 决策；后续需持久化再评估）。
4. 未实现总时间 deadline 字段（按任务要求不在本任务新增）。

### 下一步

- 按主计划执行 V2.1-T04B（Worker 抢占、heartbeat、中断恢复），本任务停止于此。

## 13. 2026-09-02 — V2.1-T04B Agent Worker、原子抢占、Heartbeat 与中断恢复

### 状态

已完成

### 目标

把 T04A 同步 Runtime 接入最小、可测试、数据库驱动的后台 Worker：原子抢占（条件 UPDATE）、步骤边界 heartbeat、stale running→interrupted 恢复、取消边界；提供最小 CLI。不实现真实 Skill/Tool/LLM/Router/API/前端。

### 源码核验

- `agent_runs` 已有 status/worker_id/heartbeat_at/started_at/finished_at 字段，且 status、heartbeat_at 已有索引（T02），无需 migration。
- AgentRunner 原无 step hook；本任务增加可选 `on_step_boundary`（默认 None，T04A 合同不变）。
- Runner 原仅允许 queued/waiting_approval 启动；本任务扩展为也允许 running（Worker 抢占后进入），终态仍拒绝。
- SQLAlchemy 2.0 条件 UPDATE（synchronize_session=False）rowcount 在 SQLite/MySQL 均可靠（claim/interrupted 必然改变 status）；heartbeat 更新值可能不变导致 MySQL rowcount=0 → heartbeat 为 best-effort，Worker 不基于其返回分支。

### 修改文件

- 修改 `backend/app/services/agent_run_service.py`：追加 next_queued_run_id / claim_queued_run / heartbeat / find_stale_run_ids / mark_interrupted（条件 UPDATE，无 SKIP LOCKED）。
- 修改 `backend/app/agents/runtime/runner.py`：on_step_boundary 可选回调 + running 状态可继续执行。
- 新增 `backend/app/workers/{__init__,agent_worker}.py`（AgentWorker + WorkerRunResult + CLI main）。
- 新增 `backend/tests/workers/test_agent_worker.py`（24 条）。
- 新增 `backend/tests/agents/test_agent_runtime_heartbeat.py`（2 条）。
- 修改 `docs/V2/{02,03,05,06,08}`。

### 数据库迁移

无。

### 验证命令与真实结果

```text
命令：python -m pytest tests -q
结果：191 passed, 37 warnings in 15.88s（165 既有 + 26 新增）
命令：git diff --check
结果：exit 0
```

### 最终接口（要点）

- `AgentWorker(session_factory, runtime_factory, worker_id, now_provider, sleeper, poll_interval_seconds, stale_after_seconds)`。
- `run_once()`：无任务返回 idle；原子抢占 rowcount==1 才成功并立即 commit；runtime 异常先 rollback 再落 failed（未知 workflow → `agent_unknown_workflow`；其他 → `agent_runtime_error`）；每次关闭 Session。
- `run_loop(stop_requested, max_iterations)`：sleeper 可注入；KeyboardInterrupt 正常退出。
- `recover_stale_runs()`：`status='running' AND (heartbeat_at < stale_before OR (heartbeat_at IS NULL AND started_at < stale_before))` → interrupted + `agent_worker_heartbeat_timeout` + finished_at；保留 worker_id；不重排。
- Heartbeat：抢占即写；步骤边界经 on_step_boundary 更新（owner-only：id + status='running' + worker_id）；waiting_approval/终态不再更新。
- CLI：`python -m app.workers.agent_worker --once / --poll-interval / --stale-after`（范围校验；Registry 为空安全 idle）。

### V1 / T01-T04A 回归

- 165 条既有测试全部继续通过（含在 191 passed 中）。V1 业务零改动。

### 并发与限制（如实登记）

- 竞争通过双 Session 模拟验证：同一候选条件 UPDATE 只有一个成功（rowcount==1）。
- 单步 heartbeat：单个外部调用超过 stale_after 的风险未解决（无独立心跳线程），登记遗留。
- heartbeat 的 MySQL rowcount 语义（更新值未变化时可能为 0）已登记，调用方不得分支。
- 不自动重排 interrupted；人工重试/重新排队留 T07 或独立任务。
- cancelled 的传播仅支持步骤边界检查（Worker 不把 cancelled 改回 running/failed）。

### 遗留问题

1. 独立 heartbeat 线程/长步骤保护未实现。
2. interrupted 后的人工重试流程未定义。
3. SQLAlchemy 2.0 的 `Session.is_active` 在 close 后仍为 True（断言需用 in_transaction），坑已记录。

### 下一步

- 按主计划执行 V2.1-T05（用例生成领域工具），本任务停止于此。

## 14. 2026-09-02 — V2.1-T05 用例生成领域工具与确定性校验器

### 状态

已完成

### 目标

把数据库读取和确定性校验封装为带权限的纯领域工具：4 个只读上下文工具 + 5 个校验/去重/覆盖/dry-run 工具；全部 Pydantic 输入/输出、只读、零副作用；不写业务用例表、不实现 LLM/Workflow/API。

### 源码核验

- `ai_service.py` 的确定性规则生成函数中，`build_case_context` / `validate_rule_generation_input` / `generate_mock_test_code` / `validate_generated_code_rules_with_reason` / `validate_python_code` 均为纯内存函数；`save_generated_code_result` 与 `generate_case_test_code_by_rule` 会写数据库与 tests_generated 文件，dry-run 必须避开。
- `function_case_service.get_function_case_list` / `api_document_service.get_api_document_list` 提供查询模式；ApiDocument 与 APICase 之间无直接外键关联（按项目/模块归属）。
- 权限规则复用 `permission_service.can_read_project`（admin/viewer 全读、tester 仅授权项目）。

### 修改文件（全部新增 + 文档）

- 新增 `backend/app/agents/tools/{__init__,base,case_context_tools,case_validation_tools}.py`
- 新增 `backend/app/agents/validators/{__init__,case_validators}.py`
- 新增 `backend/tests/agents/test_case_validators.py`（17 条）
- 新增 `backend/tests/agents/test_case_context_tools.py`（12 条）
- 新增 `backend/tests/agents/test_case_validation_tools.py`（10 条）
- 修改 `docs/V2/{02,03,05,08}`

### 数据库迁移

无。

### 验证命令与真实结果

```text
命令：python -m pytest tests -q
结果：230 passed, 38 warnings in 14.68s（191 既有 + 39 新增）
命令：git diff --check
结果：exit 0
```

### 工具清单（全部只读、Pydantic 输入/输出）

- 上下文：load_source_context（快照 + 内容哈希，哈希变化可检测来源变化）、load_project_module_context（含 module 归属校验）、list_existing_cases（限量摘要）、list_related_api_documents。
- 校验：validate_case_schema（类型/结构）、validate_case_business_rules（必填/枚举/取值）、deduplicate_cases（确定性指纹：function=名称、api=method+url；已有用例先注册指纹，与已有重复的候选被丢弃）、compute_coverage_matrix（确定性聚合 + 未知条款引用警告）、dry_run_api_case_codegen。

### dry-run 复用与零副作用证据

- 复用 `ai_service.build_case_context` / `validate_rule_generation_input` / `generate_mock_test_code` / `validate_generated_code_rules_with_reason`（均为纯内存函数）。
- 候选构造为瞬态 APICase 对象：不 add 到 Session、不 commit、不写 generated_test_code。
- 测试证据（test_dry_run_zero_side_effects）：调用前后 APICase 行数不变；monkeypatch `file_writer.save_test_code_to_file` 断言其不被调用。

### V1 / T01-T04B 回归

- 191 条既有测试全部继续通过（含在 230 passed 中）。V1 业务零改动。

### 限制与遗留问题

1. ApiDocument 与 APICase 无直接关联：list_related_api_documents 按项目/模块返回文档摘要，无法按“用例→文档”精确关联。
2. 覆盖矩阵的 covered_clause_ids 是 Workflow 提供的关联标注（T06 实现），本任务只做确定性聚合与非法引用校验。
3. dry-run 只校验“规则可生成合法 pytest 代码”，不保证运行结果；复用 V1 规则生成的全部限制（网页类 URL、变量引用等）。
4. 工具尚未接入 ToolRegistry/Workflow（T06 由 Workflow 编排调用）。
5. 保存候选工具（save_selected_candidates）不在本任务范围（写业务表必须审批，留 T07）。

### 下一步

- 按主计划执行 V2.1-T06（用例生成 Skill 与 Workflow），本任务停止于此。

## 15. 2026-09-02 — V2.1-T05.1 用例去重指纹修复

### 状态

已完成

### 修复前的误判风险

1. API 指纹只有 `method+url`：同一接口的正常、参数缺失、密码错误、边界值等不同测试场景会被误判为重复并丢弃（阻断 T06 的场景覆盖）。
2. `list_existing_cases` 的已有功能用例摘要字段是 `name`，而 `case_fingerprint` 读取 `case_name`：候选与已有功能用例无法可靠匹配。

### 新旧指纹字段差异

- 旧：`function = case_name`；`api = method + url`。
- 新：`function = case_name/name + steps_json/steps + expected_result + case_type`；`api = method + canonical URL + body + expected_result + case_type`。
- canonical 策略：JSON `sort_keys` 递归稳定序列化（key 顺序无关）；JSON 字符串先解析再 canonical、失败用原字符串 fallback；URL 经 urlsplit 规范化（scheme/netloc 小写、path 去尾斜杠、query 参数排序），含 `<<变量>>` 占位或解析失败时稳定 fallback。
- 指纹输出为 `sha256:...` 摘要：中间明文只存在于内存，去重结果与 `DuplicateRelation.fingerprint` 均不含密码/token 等明文。
- `list_existing_cases` 摘要：function 统一返回 `case_name`（不再用 `name`），两类用例都带服务端用同一算法生成的 `dedup_fingerprint`；**不返回 steps_json/expected_result/body 明文**（避免 Secret 泄露）；`find_duplicates` 对自带 `dedup_fingerprint` 的已有条目直接复用。
- 去重语义不变：已有用例优先保留；候选之间保留首个；仅 exact duplicate 去重，不使用 embedding/LLM Judge/模糊阈值。

### 修改文件

- 修改 `backend/app/agents/validators/case_validators.py`（canonical_json/canonical_url/case_fingerprint/find_duplicates）
- 修改 `backend/app/agents/tools/case_context_tools.py`（已有用例摘要字段与 dedup_fingerprint）
- 修改 `backend/tests/agents/test_case_validators.py`、`test_case_context_tools.py`、`test_case_validation_tools.py`
- 修改 `docs/V2/{02,03,05,08}`

### 数据库迁移

无。

### 新增回归测试（18 条）

同接口不同场景不误删（body/expected/case_type 差异、验收示例三条全保留）、JSON key 顺序与 URL query 顺序归一、body dict/JSON 字符串等价、已有用例摘要指纹复用、function 字段别名匹配、同名不同步骤/预期不合并、指纹与 DuplicateRelation 不含明文、输入对象不被修改。

### 验证命令与真实结果

```text
命令：python -m pytest tests -q
结果：248 passed, 37 warnings in 9.33s（230 既有 + 18 新增）
命令：git diff --check
结果：exit 0
```

### V1 / T01-T05 回归

- 230 条既有测试全部继续通过（含在 248 passed 中）。

### 仍可能存在的误判边界

1. 语义等价但字面不同的场景仍会被视为不同（如 body 字段取值顺序、不同大小写内容）——按"仅 exact duplicate 去重"原则，宁可保留也不误删；
2. `<<变量>>` URL 与解析失败的 URL 使用保守 fallback，可能漏掉部分可归一化场景；
3. expected_result 为字符串形态的 JSON 与 dict 已归一，但带空格/注释的非法 JSON 字符串无法归一。

### 下一步

- T06 未开始；等待 V2.1-T06 提示词。

## 16. 2026-09-02 — V2.1-T06 用例生成 Skill 与 Workflow

### 状态

已完成

### 目标

把 T03-T05 的基础设施串成真实、受控、可恢复的 `case_generation` Skill：显式 skill_code → AgentRun → 读取上下文 → 范围 GATE → LLM 拆解与规划 → 覆盖 GATE → LLM 生成候选 → 确定性校验/去重/覆盖/dry-run → 最多 2 轮修正 → 双 Artifact → 保存审批 GATE → waiting_approval。不写业务用例表（保存留 T07），不实现 API/前端/对话路由。

### 修改文件

- 新增 `backend/app/agents/skills/case_generation/`：`schemas.py`（State/LLM 输出/GATE resolution 合同）、`workflow.py`（状态机）、`definition.py`（SkillDefinition）、`prompt_loader.py`、`instructions.md`、`prompts/{analyze_and_plan_v1,generate_candidates_v1,repair_candidates_v1}.md`
- 新增 `backend/app/agents/bootstrap.py`（默认 Registry 显式装配：case_generation:v1 + T05 九工具）
- 修改 `backend/app/agents/runtime/contracts.py`：StepOutcome.invocations + RuntimeContext.run（兼容扩展，默认值不破坏 T04A/T04B）
- 修改 `backend/app/agents/runtime/runner.py`：invocations 落为独立 AgentStep、累计 llm/tool/token 计数
- 修改 `backend/app/agents/registry/tool_registry.py`：ToolDefinition.tool（承载工具实例，经注册表调用）
- 修改 `backend/app/services/agent_run_service.py`：start_step 序号改为 Run 内 max+1（多子步骤不冲突）
- 修改 `backend/app/services/agent_artifact_service.py`：新增 update_payload；`agent_approval_service.py`：新增 find_approval_by_action
- 修改 `backend/app/workers/agent_worker.py`：CLI 改用默认生产 Registry
- 新增 `backend/tests/agents/skills/case_generation/` 四个测试文件（40 条）
- 修改 `docs/V2/{02,03,05,06,08}`

### 数据库迁移

无。

### 验证命令与真实结果

```text
命令：python -m pytest tests -q
结果：288 passed, 39 warnings in 19.61s（248 既有 + 40 新增）
命令：git diff --check
结果：exit 0
```

### Skill/Workflow 最终状态图

`load_source → load_project_context → load_existing_cases → scope_gate(GATE1) → analyze_and_plan(LLM#1) → create_coverage_artifact → coverage_gate(GATE2) → generate_candidates(LLM#2) → validate_candidates → deduplicate → compute_coverage → api_dry_run(仅 api_document) → repair_decision(LLM#3/#4，0–2 轮) → finalize_artifacts → save_gate(GATE3) → done`

### 三个 GATE

- `confirm_case_generation_scope`：可修改 case_types/max_cases/user_goal（Pydantic 校验）；
- `confirm_case_coverage_plan`：关联 coverage_matrix Artifact，可提供经 Schema 校验的受控修改；
- `save_generated_case_candidates`：关联 test_case_set Artifact，T06 只创建 pending Approval；保存动作 T07。
- 通用规则：恢复时按 (run_id, action_code) 先查现有 Approval 绝不重复创建；approved 继续 / pending 等待 / rejected → failed(`agent_gate_rejected`)；resolution_json 一律 Pydantic 校验；GATE 写 AgentEvent。

### LLM 与 Tool 调用轨迹

- 每次 Tool/LLM 调用经 `StepOutcome.invocations` 落为独立 AgentStep（kind=llm/tool，含脱敏 input/output 摘要、duration、provider/model、token），Runner 累计 llm_calls_used/tool_calls_used/prompt_tokens/completion_tokens。
- LLM 经 LLMGateway + response_model 校验；场景复用 `requirement_to_function_case` / `api_doc_to_api_case`（保持 prompt_template 顺序）；最多 4 次调用；Workflow 内不额外重试。

### 修正与停止条件

- 触发 repair：校验错误 / 缺失覆盖 / API dry-run 失败 / 无候选；repair 只输入问题候选子集，禁止全量重生成；保留未修改候选的 candidate_id，替换候选 revision+1。
- 停止：无阻断错误且满足已确认覆盖计划；repair_round==2；llm_calls_used==4；零有效候选 → failed(`agent_no_valid_candidates`)；Runtime max_steps；用户取消。达到上限仍有缺口时保留有效候选并如实 warnings，不伪造成功覆盖。

### Artifact Schema

- coverage_matrix：atomic_clauses/coverage_plan/matrix/missing/assumptions/warnings/source_hash/prompt_version；
- test_case_set：source 信息/source_hash/candidates(含 candidate_id、revision、dry_run 结果)/validation_summary/duplicate_summary/coverage_summary/repair_round/warnings/model_metadata；状态保持 draft。
- State 存于 `output_json["workflow_state"]`（schema_version=1），恢复经 model_validate；Secret 键递归脱敏后才入 State/Artifact。

### 来源变化

finalize 时重新读取来源哈希并比较；变化则加 `source_changed` 警告、不自动重新生成；T07 保存前必须再次强制比较。

### V1 / T01-T05.1 回归

- 248 条既有测试全部继续通过（含在 288 passed 中）。V1 业务零改动。

### 尚未实现的边界

- Router/API、前端、自然语言 Skill Router（首期显式 skill_code）；
- 保存候选的业务写入与幂等保存（T07）；
- 真实 LLM/MySQL 联调。

### 遗留问题

1. GATE 决议通过审批 Service 由外部调用方（T07 API/测试）解决，触发恢复的入口仍是 Runner/Worker 调用；
2. 候选修正后的覆盖矩阵在下一轮 validate 循环重新计算（确定性正确，但每轮重算成本未优化）；
3. 来源脱敏只覆盖已知敏感键，未知自定义敏感字段需后续扩展（V2.3-T01）。

### 下一步

- 按主计划执行 V2.1-T07（会话、消息、Artifact API 与保存审批），本任务停止于此。

## 17. 2026-09-02 — V2.1-T07 会话、消息、Artifact API 与保存审批

### 状态

已完成

### 目标

暴露 Session/Message/Event/Run/Artifact/Approval API：显式创建 case_generation Run（202）、GATE 决议（approved→queued / rejected→cancelled）、保存候选（单事务 + 幂等 + source_hash 冲突保护）。不实现前端与自然语言路由；不启动后台 Worker（测试显式推进）。

### 修改文件

- 新增 `backend/app/schemas/agent.py`（请求/响应 Schema，from_attributes）
- 新增 `backend/app/services/agent_save_service.py`（保存事务与幂等）
- 新增 `backend/app/routers/agent_router.py`（14 个端点 + error_code→HTTP 映射）
- 修改 `backend/app/main.py`（注册 agent_router，其余不变）
- 修改 `backend/app/agents/runtime/contracts.py`：StepStatus 增加 `cancelled`
- 修改 `backend/app/agents/runtime/runner.py`：cancelled 分支（running/waiting_approval→cancelled + 事件）
- 修改 `backend/app/agents/runtime/transitions.py`：新增 `waiting_approval→queued`（GATE 批准交回 Worker）与 `waiting_approval→succeeded`（保存成功直接完成）
- 修改 `backend/app/agents/skills/case_generation/workflow.py`：三个 GATE rejected 从 failed 改为 **cancelled**；input 校验对 None 走默认值
- 修改 `backend/tests/conftest.py`：内存 SQLite 改用 StaticPool 共享单连接（TestClient 跨线程执行 startup，SingletonThreadPool 会导致每线程独立空库）
- 新增 `backend/tests/api/test_agent_api.py`（27 条 TestClient 集成测试）
- 更新 `backend/tests/agents/test_runtime_transitions.py`（新增合法转换）与 T06 两个 rejected 测试（failed → cancelled）
- 修改 `docs/V2/{02,03,04,05,06,08}`

### 数据库迁移

无。

### 验证命令与真实结果

```text
命令：python -m pytest tests -q
结果：316 passed, 145 warnings in 23.63s（288 既有 + 28 新增）
命令：git diff --check
结果：exit 0
```

### 最终 API 路径（prefix=/agent）

- `POST /agent/sessions`、`GET /agent/sessions`、`GET /agent/sessions/{id}`（含消息）、`GET /agent/sessions/{id}/messages?limit`、`GET /agent/sessions/{id}/events?limit`
- `POST /agent/sessions/{id}/messages`（role 强制 user；携带 skill_code+source 时创建 queued Run）
- `POST /agent/runs/case-generation` → **202 + run_id，不直接执行**；`GET /agent/runs/{id}`、`GET /agent/runs/{id}/steps`（脱敏有序）、`GET /agent/runs/{id}/artifacts`、`POST /agent/runs/{id}/cancel`
- `POST /agent/approvals/{id}/resolve`（GATE 决议）、`GET /agent/artifacts/{id}`、`POST /agent/runs/{id}/save-candidates`

### owner/project 权限

- Session 仅 owner 可见（404 隐藏）；Run/Artifact 读取 = 会话 owner 或项目读者（can_read_project）；写操作（保存/取消）经 require_project_write（viewer → 403）。
- 审批决议：owner + 仅 pending + 必须是 Run 当前 GATE（按 workflow_state.phase 判定，非当前审批 409）。

### GATE 续跑事务

- approved：approval 决议 + run waiting_approval→**queued** + 事件一个事务，交回 Worker 继续；
- rejected：approval 决议 + run → **cancelled**（不是 failed）+ 事件；
- 重复相同决议幂等（200、不重复事件）；不同决议 409；Run 取消时 pending 审批级联 cancelled。

### rejected → cancelled 修复

T06 的 GATE rejected 原先把 Run 置 failed；本任务统一为 cancelled（Workflow 输出 `StepOutcome(status="cancelled")`，Runner 新增 cancelled 分支），T06 两个 rejected 测试同步更新。

### 保存事务和幂等策略

- 校验链：owner → 审批存在 → **幂等分支**（approved 且 candidate_ids 相同 → 返回相同 saved_case_ids，resolution_json 持久化、进程重启后有效；不同 → 409）→ waiting_approval → pending → artifact 归属 → candidate_ids 合法 → source_hash 比较（变化 → 409，业务表不动）→ require_project_write。
- 单事务：业务写入（function_cases/api_cases，source="llm"，数据全部取自 Artifact/Run，不信任前端 payload/project_id）+ artifact saved + approval approved（resolution_json={candidate_ids, saved_case_ids}）+ run succeeded + cases_saved 事件一次；异常整体回滚（测试注入构造失败验证零残留）。

### 其他记录

- HTTP 合同：400/401/403/404/409/422/500；AgentError.error_code 映射；未预期异常回滚后返回 500 安全消息。
- conftest StaticPool 修复：TestClient 跨线程 startup 下内存 SQLite 共享问题（坑已登记）。
- V1 业务零改动；T01 Baseline 继续通过。
- refine 端点与对话路由未实现（前端与自然语言路由留 T08）。

### 遗留问题

1. refine（局部修正）端点未实现（T08 前端交互确定后再定合同）。
2. 消息启动 Run 的响应为 200（含 run 信息），未单独返回 202——保持消息语义，可后续调整。
3. 保存幂等依赖 resolution_json 中持久化的 saved_case_ids，若未来需要跨审批复用需评估独立幂等表（当前字段够用）。

### 下一步

- 按主计划执行 V2.1-T08（Agent 对话工作台与结构化 Artifact 前端），本任务停止于此。

## 18. 2026-09-03 — V2.1-T08 悬浮 Agent 工作台与前后端联调

### 状态与范围

主闭环完成隔离联调。Codex 负责前端和小范围 T07 合同补齐；未替换 Claude 的 Runtime、Worker 或保存 Service。没有新依赖、迁移或真实环境操作，没有重跑 T01–T07 全量后端测试。

### 实现与修复

- `frontend/src/components/test-agent/`：悬浮窗口、对话、三种 GATE 卡片、候选/覆盖产物、进度、会话生命周期 Hook、合同转换与样式。
- `frontend/src/api/agent.js`：对齐实际创建 Run、审批和保存 API。保留 `App.jsx` 的登录后全局挂载及需求/接口文档“交给 Agent”入口。
- `backend/app/routers/agent_router.py`：新增会话 Run 列表和 Run 审批列表（owner-only）；取消补 owner 校验；禁止通用审批绕过保存事务。
- 修复预期 API 与实际路径/字段不一致、候选嵌套字段漏展示、覆盖矩阵误读、刷新无法恢复、跨会话旧响应回写、原生缩放尺寸抖动、保存后产物自动隐藏和勾选状态丢失。
- 范围类型/数量/目标可编辑，覆盖计划可取消条目；待审批任务不允许切换来源，错误在小屏产物模式也可见；中文输入法选字不触发 Enter 发送。

### 新增验证资产

- `frontend/tests/agentContract.test.mjs`：6 条 Node 内置测试，无需新增测试框架。
- `backend/tests/api/test_agent_api.py`：追加 2 条 integration_ 测试（恢复查询权限、禁止绕过保存审批）。
- `backend/tests/manual/agent_preview_server.py`：本地临时 SQLite / Fake Gateway / 固定测试用户，实际 Agent Router + Worker；独立入口，不导入生产 app.main。
- `frontend/agent-integration.html` 与 `src/integration/agentPreview.jsx`：开发环境专用页面，生产构建不引用。

### 实际结果

```text
frontend: node --test tests/agentContract.test.mjs
6 passed, 0 failed

backend: python -m pytest tests/api/test_agent_api.py -q -k integration_
2 passed, 27 deselected, 25 warnings in 2.11s

frontend: npx eslint src/components/test-agent src/api/agent.js src/integration/agentPreview.jsx tests/agentContract.test.mjs
exit 0

frontend: npm run build
exit 0（保留 bundle > 500 kB 警告）
```

浏览器经过真实 HTTP 和 Worker 验证：需求生成 2 条仅选 1 条实际保存；接口生成 2 条实际保存；范围修改、覆盖确认、刷新恢复、历史切换、来源变化拒绝保存且零新增、停止后重新开始。窗口拖动/缩放、最小化/恢复、最大化与 390×844 小屏检查通过。详细操作与边界见 `09_FRONTEND_BACKEND_INTEGRATION.md`。

### 尚未完成

真实 MySQL/供应商/正式登录整页联调；自由局部 refine 和多 Skill 自然语言路由；长会话分页和任意历史 Run 切换；T09 影子评测与发布验收。不能把本次 Fake LLM 链路验证写成真实模型效果达标。

## 19. 2026-09-03 — V2.1-T08.1 修复正式环境 Agent 创建会话 500

### 已证实的直接原因

真实 MySQL `ai_test_assistant`（backend/.env 指向）只读核查结果：

- `projects` 表 0 行：id=1 与 id=2 都不存在；
- `requirement_docs` id=1、id=2 均存在，`project_id=2`、status=confirmed、未删除；
- user id=1 为 system_admin；`api_documents`、`agent_sessions/runs/messages` 均 0 行。

即：`POST /agent/sessions`（project_id=2）插入 `agent_sessions.project_id`（FK → `projects.id`）时引用了**不存在的项目行**，MySQL 报 `IntegrityError 1452`，旧代码未捕获 → 500。`agent_session_service.create_session` 原先直接 add/flush，无任何项目前置校验。

前端传值链已核实正确：需求/接口页均以 `record.project_id` / `record.id` 派发，widget 用 `context.projectId` 调会话创建，**不是把需求 ID 当项目 ID**。软删除也非本次原因（该库根本没有对应项目行）。`requirement_docs`/`api_documents` 的 `project_id` 是无外键普通列且 CRUD 不校验项目行存在，因此孤立引用可长期存在——这是**上游尚未修复的数据治理缺口**（见下）。

### 修改文件

- `backend/app/services/agent_session_service.py`：新增 `validate_project_for_session`（存在/未删除/active）、`resolve_session_source`（来源形状校验）、`validate_session_source`（来源存在/未删除/归属项目与请求一致，以服务端查询为准）；`create_session` 调用项目预检。
- `backend/app/routers/agent_router.py`：`create_session_api` 顺序执行 项目存在与状态 → `require_project_write`（沿用项目内创建/生成的可操作权限语义，不提升 viewer/admin）→ 来源校验 → 插入；`IntegrityError` 兜底回滚并返回稳定 409；`_ERROR_STATUS` 增加 `agent_project_not_found=404`、`agent_project_inactive=400`、`agent_source_mismatch=400`。
- `frontend/src/components/test-agent/agentContract.js`：新增 `sessionStartErrorText`，把会话/来源启动失败的 4xx/5xx 转成含处理建议的中文提示。
- `frontend/src/components/test-agent/useAgentSession.js`：创建会话遇 4xx（项目/来源失效或无权）时清空本次来源上下文并终止，不继续创建 Message/Run，不残留无效本地会话。
- `backend/tests/conftest.py`：隔离 SQLite 开启并断言 `PRAGMA foreign_keys=ON`（对齐 MySQL，避免再漏 FK 类问题）。
- 既有测试适配（因隔离库开启外键、`create_session` 增加项目预检）：`test_agent_platform_services.py`、`test_agent_worker.py`、`test_agent_runtime.py`、`test_agent_runtime_heartbeat.py` 的会话 seed 补 users/projects 父行；`test_agent_api.py` 中两处故意写“不存在 Artifact/非当前 save 审批”的测试改为外键合法但语义相同的构造（其他 Run 的 Artifact、scope 阶段伪造 coverage 审批）。
- `backend/tests/api/test_agent_api.py`、`backend/tests/services/test_agent_platform_services.py`：新增针对性用例（见下）。

### 实际执行与结果

```text
backend（项目 venv）:
python -m pytest tests/api/test_agent_api.py tests/services/test_agent_platform_services.py -q
64 passed
python -m pytest tests/workers tests/agents tests/models/test_agent_platform_models.py \
             tests/migrations/test_agent_platform_migration.py tests/api/test_agent_api.py \
             tests/services/test_agent_platform_services.py -q
250 passed
python -m pytest tests/services tests/providers tests/agents/skills -q
149 passed
（均为一次性确认隔离库外键开启后无连带破坏；未调用真实 LLM、未访问业务接口、未写真实 MySQL）

frontend:
node --test tests/agentContract.test.mjs
9 passed（原 6 + 新增 3）
npx eslint src/components/test-agent/agentContract.js src/components/test-agent/useAgentSession.js tests/agentContract.test.mjs
exit 0
```

覆盖：合法项目+来源成功；不存在项目 404 且零新增会话；孤立需求（引用不存在项目）场景 404 非 500；来源不存在/已删除、项目已删除；来源项目与请求项目不一致；无写权限 403；非法请求后同一 DB 后续合法请求仍成功（事务不污染）；无来源会话仍兼容；既有 Run+Fake Worker 到 GATE 链路回归（250 通过的 API/integration 用例）。

### 仍待用户决策的历史数据

本次只让错误“可理解、可避免”，**不能自动恢复** requirement_docs id=1、id=2 的归属：这两条需求当前都指向不存在的 project_id=2，在项目数据恢复或迁移前，无法对它们正常生成用例。可选处置（需授权后由人执行）：

1. 恢复/新建 id=2 的项目并将这两条需求归回，或
2. 将需求迁移到真实存在的项目并更新其 `project_id`。

此外，`requirement_docs`/`api_documents` 等业务来源表对 `project_id` 无外键且 CRUD 不校验项目行存在，是产生孤立数据的上游治理缺口，建议后续单独立项（数据层加校验或迁移约束），本次未改以免扩大范围。

### 尚未完成/边界

- 真实项目数据未写入（零 projects 时管理员也需先有项目才能建会话）；真实 MySQL 写入与模型调用不在本任务授权内。
- 不对会话已存在但来源随后被删的“运行期”再做额外幂等兜底（现有 run-create 已校验来源），不在本任务额外开发。
