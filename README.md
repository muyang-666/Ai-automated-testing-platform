# TestMind

面向测试人员的 AI 工作平台。当前研发顺序：

**V1 既有测试平台 → V2 对话式 Test Agent 与可持续测试资产 → V3 更高级测试能力。**

> 2026-09-03：V2 参考 Pi 的核心架构，用 Python 实现，不嵌入 Pi Node SDK。
> 2026-09-04：V2-P01～P04（消息 / Provider / Agent Loop / 会话持久化）已通过各自范围验收；P05 起进入“对话式 Test Agent + Test Artifact 协作编辑”新路线（[方向 ADR](docs/V2/11_V2_DIRECTION_ADR.md)、[P05～P10 路线](docs/V2/12_POST_P04_DEVELOPMENT_PLAN.md)）。基础测试设计与用例协作编辑现在是 V2 的纵向闭环；固定 case_generation Workflow 退役为 legacy；API 测试、失败根因、造数、缺陷、执行/CI 等更高级能力归 V3。

## 项目入口

- [总项目记录](docs/PROJECT_RECORD.md)
- [V2 主计划：V2-P01～P10](docs/V2/01_AGENT_DEVELOPMENT_PLAN.md)
- [V2 方向 ADR 与 P05～P10 路线](docs/V2/12_POST_P04_DEVELOPMENT_PLAN.md)
- [Pi 源码与 Python 映射](docs/V2/10_PI_SOURCE_AUDIT.md)
- [V3 高级测试能力计划](docs/V3/01_TEST_CAPABILITY_PLAN.md)
- [旧版本记录归档](docs/archive/PRE_PI_V2_2026-09-03/ARCHIVE_NOTICE.md)

## V1 已有平台

项目/模块/用户/权限、需求和接口文档、用例管理、一次 LLM 生成、pytest 代码生成与执行、场景串联、失败日志分析和报告。

## V2 对话式 Test Agent

正常多轮聊天、模型文本与工具调用、受控执行循环、Skill 按需加载、事件流、持久化、取消/恢复、上下文压缩和安全门禁；
TestArtifact（测试点/用例树）是一等业务对象，Agent 通过增量 Artifact 工具编辑它，产生 Revision / Diff / Undo，并在 Chat + MindMap + Diff 工作台里与用户共同维护。
普通聊天无需需求文档；文本回复不要求 JSON，程序消费的工具参数仍严格校验。测试设计不是固定 Workflow：模型决定下一步，程序保证安全，Artifact 保存演进结果。

Pi 参考源码在 D:\pi，与本仓库分开；不需要安装或运行该仓库。具体固定提交见源码映射文档。

## V3 高级测试能力

- V3.1：API Testing Agent。
- V3.2：Failure RCA（失败根因分析）。
- V3.3：Test Data（测试数据/造数）。
- V3.4：Defect Assistant（缺陷辅助）。
- V3.5：Execution / CI Integration。

这些更高级测试能力统一复用 V2 的 Conversation + Agent Loop + Tools + Artifact 模型，不再为单个功能新建固定 Workflow Runtime。它们仍是版本目标，不代表已完成；基础测试设计与用例协作编辑已在 V2 闭环内。通用身份隔离、预算和审批机制属于 V2，不能延期到业务版本才补。

## 技术栈

后端：Python、FastAPI、SQLAlchemy、MySQL、Pydantic、Alembic、httpx、pytest。
前端：React、Vite、Ant Design、Axios。
不新增 Node 后端，不声称兼容 Pi 的全部插件、TUI 或宿主工具。

## 本地启动（现有兼容基线）

先检查 backend/.env 的数据库和模型配置。数据库迁移、演示 seed 和真实模型调用不是本 README 授权的自动动作；旧空库迁移接管边界见历史文档。

终端一：

~~~powershell
cd D:\Ai-test-assistant\backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8001
~~~

终端二：

~~~powershell
cd D:\Ai-test-assistant\backend
..\.venv\Scripts\python.exe -m app.workers.agent_worker
~~~

终端三：

~~~powershell
cd D:\Ai-test-assistant\frontend
npm run dev
~~~

以上假设项目虚拟环境和前端依赖已经安装；启动会读取实际配置，Worker 会消费排队任务。现有入口能运行不代表新 V2 对话内核已实现。
旧隔离用例联调入口只用于历史基线，不作为新 V2 验收。新的分层验证见 [V2 联调计划](docs/V2/09_FRONTEND_BACKEND_INTEGRATION.md)。

## 开发原则

一次一个明确任务；先核验源码，再实施与验证。保留旧业务和用户修改，不提交密钥、不默认访问实习数据、不自动写真实环境。只把实际完成的行为标记为已实现。
