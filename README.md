# TestMind

一个面向测试人员的 **AI 测试 Agent 工作平台 V2**。

TestMind 在现有接口自动化测试闭环之上，引入受控 Agent 工作流，将 AI 能力从“单次调用 LLM 生成结果”升级为“主动获取上下文、调用测试工具、验证结果、发现缺口并有限修正”的可追踪执行过程。

> 当前状态：V1 自动化测试闭环已具备，V2 Agent 能力正在规划与建设中。总项目记录见 `docs/PROJECT_RECORD.md`，Claude Code 执行计划见 `docs/V2/01_AGENT_DEVELOPMENT_PLAN.md`。

## 项目简介

TestMind 面向接口测试、功能测试和测试结果分析场景，目标是降低测试用例设计、自动化脚本生成、失败定位和测试报告整理的使用门槛。

V2 核心闭环：

```text
需求文本 / 接口文档
  → 用例生成 Agent 分析测试点与覆盖范围
  → 生成、校验、去重并修正候选用例
  → 测试人员审核并保存用例
  → 规则生成 pytest 测试代码
  → pytest / 场景链路执行
  → 根因分析 Agent 收集并验证失败证据
  → 生成结构化根因结论与测试报告
```

V2 更适合作为：

- 面向测试开发场景的 AI Agent 应用
- 接口自动化测试与场景测试平台
- AI 用例设计、覆盖检查和失败诊断工具
- 可追踪、可评测、有人机协同边界的测试 Agent 原型

## V1 已有能力

- 项目与多级模块管理
- 接口测试用例 CRUD
- 需求文本、接口文档和功能测试用例管理
- LLM 生成功能测试用例和接口测试用例
- 生成结果预览、勾选与保存
- 规则生成 pytest 测试代码
- 测试代码落盘与持久化保存
- pytest 动态执行与执行记录管理
- 接口响应状态码和响应体采集
- 场景步骤编排、变量提取、断言和真实串联执行
- AI 失败日志分析
- 测试报告生成与查询
- 用户、角色和项目权限管理
- LLM Provider、模型和业务场景配置

## V2 核心能力

### AI 用例生成 Agent

- 读取需求、接口文档、项目、模块和已有用例上下文
- 将输入拆解为可追踪的原子需求与接口约束
- 规划正常、异常、边界、鉴权和业务规则等覆盖维度
- 生成结构化候选用例
- 调用本地工具执行 Schema、业务规则、重复度和覆盖度校验
- 对覆盖缺口和非法候选进行有限的定向修正
- 展示覆盖矩阵、假设和校验警告
- 保留人工勾选与保存，不允许 Agent 自动落库

### AI 测试失败根因分析 Agent

- 加载运行快照、用例、实际请求与响应、pytest 日志和执行代码
- 确定性解析 traceback、异常类型、expected/actual 和断言结果
- 静态检查请求构造、参数引用和测试代码问题
- 对比同一用例的历史运行，识别稳定回归、偶发失败和环境波动
- 分析场景上游步骤、变量提取和链路依赖
- 验证候选根因的支持证据与反证
- 输出主根因、细分类、置信度、风险等级、证据和修复建议
- 证据不足时返回 `inconclusive`，避免强行归因

### Agent 运行与治理

- Agent 任务与步骤状态持久化
- 最大步骤、模型调用、工具调用、token 和总时长限制
- 任务取消、超时和异常恢复
- 模型、Prompt 和输入版本追踪
- 工具调用、校验结果、耗时和错误记录
- 项目权限隔离和敏感信息脱敏
- 用户反馈与离线评测数据沉淀
- 保留 V1 链路作为 Baseline 和回滚入口

## Agent 设计原则

TestMind V2 采用 **受控单 Agent**，而不是开放式多 Agent 自由协作：

- 工作流由代码定义并进行版本管理
- Agent 只能调用白名单领域工具
- 工具参数使用 Pydantic 校验
- 每次工具调用重新检查项目权限
- 需求、日志和响应均按不可信数据处理
- 保存用例和主动重跑必须经过人工审批
- 修正和重试次数有限，禁止无限循环
- 只记录可观察轨迹，不保存模型隐藏思维链
- 优先使用确定性校验，LLM Judge 只作为补充

V2 首期不引入多 Agent、长期记忆、向量数据库、任意 SQL、Shell 或文件系统工具。

## 系统架构

```text
React 前端
  └─ Agent 运行面板 / 覆盖矩阵 / 根因证据视图
       ↓
FastAPI Agent API
  ├─ 创建、查询、取消和审批 Agent 任务
  ├─ 项目权限校验
  └─ 兼容原有业务接口
       ↓
Agent Runtime
  ├─ Case Generation Workflow
  ├─ Failure RCA Workflow
  ├─ LLM Gateway
  ├─ Tool Registry
  ├─ Validators / Guardrails
  └─ Agent Worker
       ↓
MySQL
  ├─ 现有项目、用例、文档和执行数据
  └─ agent_runs / agent_steps / agent_feedback
```

## 技术栈

### 后端

- Python
- FastAPI
- SQLAlchemy
- MySQL
- Alembic
- Pydantic
- pytest
- httpx

### Agent 与 LLM

- 代码定义的有限状态工作流
- 白名单领域工具
- Pydantic / JSON Schema 结构化输出
- OpenAI-compatible LLM API
- MySQL 持久化任务状态与运行轨迹

### 前端

- React
- Vite
- Axios
- Ant Design

## 项目结构

```text
backend/              后端服务
  app/agents/         Agent 工作流、工具和校验器（V2）
  app/workers/        Agent 后台任务执行器（V2）
  app/routers/        FastAPI 路由
  app/services/       业务服务与 LLM 调用
  app/models/         SQLAlchemy 数据模型
  app/schemas/        Pydantic 请求与响应模型
  app/tests_generated/ 规则生成的 pytest 文件
  tests/              平台测试与 Agent 评测（V2）
frontend/             React 前端
docs/
  PROJECT_RECORD.md   总项目记录与版本入口
  V1/                 V1 历史需求、状态、变更和验收
  V2/                 V2 Agent 计划、开发记录和验收
```

## 本地启动

### 1. 配置数据库

后端默认使用 MySQL：

```text
mysql+pymysql://root:123456@127.0.0.1:3306/ai_test_assistant?charset=utf8mb4
```

如本机 MySQL 密码不同，复制 `backend/.env.example` 为 `backend/.env` 后修改 `DATABASE_URL`。

```powershell
Copy-Item backend/.env.example backend/.env
```

### 2. 启动后端

```powershell
Set-Location backend
pip install -r requirements.txt
python scripts/seed_demo_data.py
uvicorn app.main:app --reload --port 8001
```

### 3. 启动前端

```powershell
Set-Location frontend
npm install
npm run dev
```

### 4. 启动演示被测服务（可选）

```powershell
Set-Location backend
uvicorn app.main:app --reload --port 8002
```

如需让演示用例请求第二套后端：

```powershell
$env:DEMO_TARGET_BASE_URL = "http://127.0.0.1:8002"
python scripts/seed_demo_data.py
```

## V2 实施路线

1. **基础收口**：引入 Alembic、统一 LLM Gateway、补充运行快照和自动化测试。
2. **Agent Runtime**：实现任务状态、运行步骤、预算、取消、权限和脱敏。
3. **用例生成 Agent**：实现需求拆解、覆盖规划、历史检索、校验和有限修正。
4. **根因分析 Agent**：实现证据收集、静态预诊断、历史对比和结构化归因。
5. **评测与灰度**：使用固定样本对比 V1 one-shot Baseline，指标达标后再切换默认入口。

## 评测维度

V2 不只检查最终文本，还评估：

- 最终任务结果是否正确
- 用例覆盖率、重复率和可执行性
- 根因分类、证据正确率和置信度校准
- 工具选择、参数和关键步骤是否正确
- 跨项目权限与敏感数据保护
- 异常恢复与重复运行稳定性
- 延迟、token 和模型调用成本

结构、安全、权限和资源限制作为硬门禁；生成质量和诊断准确率先与 V1 Baseline 对比，再确定正式上线阈值。

## 项目定位

TestMind V2 的目标不是让模型替代测试人员，而是让 Agent 承担重复的信息整理、覆盖检查和证据调查工作，并把最终判断、保存和高风险操作保留给测试人员。

项目最终希望形成一个 **可运行、可解释、可追踪、可评测、可安全回滚** 的测试 Agent 闭环。

