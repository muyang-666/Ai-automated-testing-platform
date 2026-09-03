# 新 V2 开发记录：Python Agent 基础

> 更新：2026-09-03。旧路线记录已原文归档，不删除其中最新修复与测试证据。
> 当前唯一完成事项：源码阅读、参考仓库克隆、版本与任务规划，以及 V2-R01 目录整理（纯结构，非对话内核验收）。以下 P 代码任务均未验收。

## 1. 当前任务状态

| 编号 | 内容 | 状态 | 证据 |
|---|---|---|---|
| V2-R01 | Agent / LLM 模块目录整理（结构，先于 P01） | 已完成 | 6 条结构测试 + 338 条受影响/回归通过，见 2.1 |
| V2-P01 | 基线与数据合同 | 待实施 | — |
| V2-P02 | 流式 Provider | 待实施 | — |
| V2-P03 | Agent Loop / Tool Executor | 待实施 | — |
| V2-P04 | 会话存储与迁移 | 待实施 | — |
| V2-P05 | Worker、租约和取消 | 待实施 | — |
| V2-P06 | 对话 API 与前端 | 待实施 | — |
| V2-P07 | Skill 基础能力 | 待实施 | — |
| V2-P08 | 上下文和压缩 | 待实施 | — |
| V2-P09 | 门禁与故障加固 | 待实施 | — |
| V2-P10 | 基础版本验收 | 待实施 | — |

## 2. 2026-09-03 — 重新划分 V2/V3 并阅读 Pi

用户授权：重写 V2 文档为 Pi 基本架构的 Python 实现；测试能力后移到 V3；克隆 Pi 到 D 盘。

实际工作：
- 通过 GitHub 与官方内容 API 阅读 Agent/Loop/消息/Skill/会话/压缩源码；
- git clone https://github.com/earendil-works/pi.git D:\pi 成功，origin 正确，参考 HEAD 为 f41f80466e30f21cdcd4d52aba4a2c2cb6ee3cc6；
- 已检查关键模块与早先读取提交的差异为空，参考仓库工作区干净；没有执行 npm install/build/test；
- 旧 V2 全部文档和旧根入口完整归档，包含旧 02 中创建会话 500 与空响应修复记录；
- 新 V2 任务使用 P 编号，新增 V3 测试路线，原用例代码作为复用资产；
- 仅修改文档，不修改后端/前端代码，不运行真实模型、不操作业务数据库、不额外 git commit/push。

验证：只做归档内容保全、链接/路线一致性和变更范围检查；这是文档检查，不是新 Agent 功能测试。最终检查结果由本次交付说明记录，后续每个任务另写实际命令。

本次检查结果：
- 21 份旧文档快照与调整前工作区正文一致（规范化行结束和 EOF 空白后比较，0 个差异）。
- 22 份当前入口文档中检查 65 个本地 Markdown 链接，0 个断链。
- 当前路线 README/docs 的 git diff --check 通过；原业务代码的未提交改动仍保留。
- D:\pi 的 origin/HEAD 已核对，git status --short 为空；未安装依赖、未运行 Pi 或项目测试。

## 3. 旧成果与未解决问题

[旧开发记录](../archive/PRE_PI_V2_2026-09-03/02_DEVELOPMENT_RECORD.md)保留旧任务编号、日期、测试命令和问题。不要将其中 33/50/102/288 等历史测试数汇总为新 V2 验收数。

可复用：Gateway、Agent 表/Service、原子抢占、用例确定性工具和已有前端。
待补：真正的文本对话循环、模型工具回传、无项目聊天、流式适配、可靠事件恢复、租约/取消、通用 Skill。
现场环境仍须核查：模型空响应原因、模型场景绑定、Worker 启动、MySQL 与孤立业务引用。重规划不等于这些问题已修复。

## 4. 后续任务记录模板

每个 V2-Pxx 追加：授权范围 → 修改前事实 → 上游参考 commit/文件 → 实际文件 → 迁移/兼容 → 实际命令/结果 → 已知差异 → 下一项边界。
新任务证据不得覆盖本次归档。

## 2.1 2026-09-03 — V2-R01 Agent / LLM 模块目录整理

### 授权与范围

纯结构整理：保留 routers/schemas/services/models 分层，在内部按 Agent、LLM 归类。只移动文件、补包导出、更新导入与文档，不改变任何业务行为、API 合同、表结构或 Prompt/审批规则。不动 D:\pi、不接 npm、不操作真实数据库/模型/运行服务。

### 实际文件映射（旧 → 新）

| 类 | 迁移 |
|---|---|
| models/agent | agent_session / agent_message / agent_run / agent_step / agent_event / agent_artifact / agent_approval.py |
| models/llm | llm_provider / llm_model / llm_scene_config.py |
| services/agent | agent_session_service / agent_run_service / agent_artifact_service / agent_approval_service.py |
| services/llm | llm_config_service / llm_client_service / llm_gateway.py |
| schemas/agent | schemas/agent.py → agent/api.py；agent_platform.py → agent/platform.py（api.py 为唯一 API Schema 实现，包 __init__ 仅显式重导出） |
| schemas/llm | llm_config.py、llm_gateway.py |
| routers/agent | agent_router.py |
| routers/llm | llm_config_router.py |

未移动：agent_save_service.py（测试候选保存业务，保留在 services 根，仅更新其内部 import）；app/agents/ 全部（执行内核与既有 Workflow）；app/workers、app/core、app/exceptions、app/utils；用户/项目/用例/执行/报告模块；tests 目录位置。

### 验证

- 迁移前对 23 个文件做 sha256 快照，迁移后逐一比对内容一致（0 差异）。
- 全仓库旧路径引用扫描 = 0；models/__init__.py 原公开模型名指向同一模型类；Base.metadata 无重复注册。
- 新增 `backend/tests/structure/test_v2_r01_structure.py` 结构测试（6 条）：新路径导入、schemas/agent 包级重导出同实现、模型身份与 metadata、路由无重复与关键端点存在、Prompt 仍可加载、llm_client_service monkeypatch 目标即实际模块。
- 实际命令与结果见下；代表性旧功能生成链路（function_case / api_document 生成 service）保留并通过，确认 monkeypatch 仍作用于真实模块。

```text
（backend，项目 venv，隔离 SQLite）
pytest tests/structure/test_v2_r01_structure.py -q
6 passed
pytest tests/structure tests/models/test_agent_platform_models.py tests/migrations/test_agent_platform_migration.py \
       tests/services/test_agent_platform_services.py tests/services/test_llm_gateway.py \
       tests/services/test_function_case_generation_service.py tests/services/test_api_document_generation_service.py \
       tests/providers tests/agents tests/workers tests/api/test_agent_api.py -q
338 passed
```

### 目录说明（结构性分组，不等于依赖解耦）

- `app/services/agent`：Agent 平台应用服务（会话/Run/Artifact/审批数据访问）。
- `app/agents`：执行内核（Runtime/Registry/工具）及既有 case_generation Workflow 资源；与 services/agent 职责不同。
- 分组只解决“文件归属”，未引入 Repository/DDD，也未消除模块间真实耦合；新 V2-Pxx 继续在既有代码上推进。

### 未提交说明

V2-R01 之上仍保留他人/本轮的未提交改动（旧 Agent 空响应可恢复重试与失败诊断、前端失败提示、文档规划与归档等）；未 commit/push，未进入任何 P 任务，等待检查。
