# 06 — 当前状态

> 更新日期：2026-05-02

## 当前阶段

**第二阶段已完成，准备进入第三阶段** — 真实接口串联与场景执行增强。

---

## 一、第二阶段已完成内容

**第二阶段名称：「需求文本管理 + 功能测试用例管理 + 需求生成测试用例」**

### 1.1 后端

| 任务 | 内容 | 关键文件 |
|------|------|---------|
| RequirementDoc CRUD | `requirement_docs` 表 + 5 个 REST 接口（增/查列表/查详情/改/软删除）+ 6 个筛选参数 | `models/requirement_doc.py`, `schemas/requirement_doc.py`, `services/requirement_doc_service.py`, `routers/requirement_doc_router.py` |
| FunctionCase CRUD | `function_cases` 表 + 5 个 REST 接口 + 9 个筛选参数 + case_code 字段 + steps_json/test_data_json JSON 类型 | `models/function_case.py`, `schemas/function_case.py`, `services/function_case_service.py`, `routers/function_case_router.py` |
| LLM 需求生成功能用例 | `POST /function-cases/generate-from-requirement` — 根据需求文本调用 LLM 生成结构化功能用例 JSON（不写表）；3 级 JSON 解析回退 | `schemas/function_case_generation.py`, `services/function_case_generation_service.py` |
| 保存生成用例 | `POST /function-cases/save-generated` — 批量保存勾选的 LLM 生成功能用例，source=llm，project_id 以需求为准 | `services/function_case_generation_service.py`, `routers/function_case_router.py` |
| 主入口注册 | 在 `main.py` 注册 RequirementDoc 和 FunctionCase 模型及路由 | `main.py` |

### 1.2 前端

| 任务 | 内容 | 关键文件 |
|------|------|---------|
| RequirementPage | 需求文本管理页面：项目选择、模块树筛选、keyword/status/type 筛选、CRUD、详情弹窗 | `pages/RequirementPage.jsx`, `api/requirement.js` |
| FunctionCasePage | 功能测试用例管理页面：项目选择、模块树筛选、需求筛选、多条件筛选、JSON 字段处理、查看详情 | `pages/FunctionCasePage.jsx`, `api/functionCase.js` |
| RequirementPage "生成用例" | 操作列增加"生成用例"按钮 → LLM 生成预览弹窗 → 勾选保存 | `pages/RequirementPage.jsx`（追加） |
| 导航更新 | App.jsx 增加"需求管理"和"功能用例"入口 | `App.jsx` |

### 1.3 保留的核心链路（零改动）

以下文件在第二阶段**仍未修改**：

| 文件 | 承载的链路 |
|------|-----------|
| `backend/app/services/ai_service.py` | LLM 代码生成 + 规则生成（第二阶段仅调用 `call_llm_generate_code`，不修改） |
| `backend/app/services/run_service.py` | 测试执行编排 |
| `backend/app/services/analysis_service.py` | AI 失败分析 |
| `backend/app/services/report_service.py` | 项目报告生成 |
| `backend/app/utils/pytest_runner.py` | pytest subprocess 执行器 |
| `backend/app/utils/file_writer.py` | 测试代码文件落盘 |

---

## 二、第二阶段明确未做

以下功能明确不在第二阶段范围，未实现：

1. 功能测试用例不执行
2. 功能测试用例不生成 pytest
3. 不做 UI 自动化
4. 不改接口测试执行链（run_service / pytest_runner 未改）
5. 不改 analysis_service.py
6. 不改 report_service.py
7. 不做用户登录和权限
8. 不做报告按项目统计增强
9. 不做真实接口串联
10. 不做场景按项目过滤
11. 不改 CasePage / FunctionCasePage 已有结构

---

## 三、下一阶段目标

**第三阶段：「真实接口串联与场景执行增强」**

计划内容：
1. 场景表增强：增加 `project_id`、`module_id`、`status`、`is_deleted`
2. 场景步骤表增强：增加步骤名称、变量提取规则、请求覆盖配置、断言规则、启用状态
3. 实现运行时 context（变量池）
4. 支持从上一步响应中提取变量（如 token、user_id）
5. 支持在后续请求中使用 `${变量名}` 进行参数替换
6. 支持 httpx 顺序执行场景步骤（不改 run_service，新增串联执行器）
7. 保存每一步请求、响应、提取变量、断言结果
8. 生成可查看的场景执行结果（增强展示）
9. 前端场景管理页面增强（项目筛选、模块树、步骤配置增强）
10. 保留第一阶段、第二阶段所有能力

---

## 四、核心文件禁止修改规则（延续至第三阶段）

以下 6 个文件在第三阶段仍**禁止修改**，除非明确解禁：

| 禁止修改的文件 | 承载的链路 | 禁止级别 |
|---------------|-----------|---------|
| `backend/app/services/ai_service.py` | LLM 代码生成引擎 + 规则生成引擎 | 🔴 完全禁止 |
| `backend/app/services/run_service.py` | 测试执行编排 | 🔴 完全禁止 |
| `backend/app/services/analysis_service.py` | AI 失败分析 | 🔴 完全禁止 |
| `backend/app/services/report_service.py` | 项目报告生成 | 🔴 完全禁止 |
| `backend/app/utils/pytest_runner.py` | pytest subprocess 执行器 | 🔴 完全禁止 |
| `backend/app/utils/file_writer.py` | 测试代码文件落盘 | 🔴 完全禁止 |

> **规则**：第三阶段如需实现场景串联执行，不允许通过修改以上 6 个文件来实现。可在 `scene_service.py` 中新增串联执行函数，或新增独立的串联执行器。

---

## 功能清单（第二阶段完成后）

| 功能模块 | 状态 | 关键文件 |
|---------|------|---------|
| 用例 CRUD | ✅ 正常（支持项目/模块筛选 + 新字段） | `routers/case_router.py`, `services/case_service.py` |
| LLM 生成 pytest 代码 | ✅ 正常 | `routers/ai_router.py`, `services/ai_service.py` |
| 规则生成 pytest 代码 | ✅ 正常 | `routers/ai_router.py`, `services/ai_service.py` |
| pytest 执行 | ✅ 正常 | `routers/run_router.py`, `services/run_service.py`, `utils/pytest_runner.py` |
| 响应采集 | ✅ 正常 | `utils/pytest_runner.py` |
| AI 失败分析 | ✅ 正常 | `routers/ai_router.py`, `services/analysis_service.py` |
| 场景管理 | ✅ 正常 | `routers/scene_router.py`, `services/scene_service.py` |
| 场景执行 | ✅ 正常 | `services/scene_service.py` |
| 报告生成 | ✅ 正常 | `routers/report_router.py`, `services/report_service.py` |
| 参数管理 | ✅ 正常 | `routers/parameter_file_router.py`, `utils/parameter.py` |
| 项目管理 | ✅ 正常 | `routers/project_router.py`, `services/project_service.py` |
| 模块目录树 | ✅ 正常 | `routers/module_router.py`, `services/test_module_service.py` |
| 需求文本管理 | ✅ 新增 | `routers/requirement_doc_router.py`, `services/requirement_doc_service.py` |
| 功能测试用例管理 | ✅ 新增 | `routers/function_case_router.py`, `services/function_case_service.py` |
| 需求生成功能用例 | ✅ 新增 | `services/function_case_generation_service.py` |
| 前端 9 页面 | ✅ 正常 | `frontend/src/pages/*.jsx` |

---

## 数据库当前状态

SQLite 单文件 `ai_test_assistant.db`，10 张表：

```
api_cases          — 接口测试用例（已增加 project_id / module_id / case_type / source / priority / status / is_deleted）
test_runs          — 执行记录
ai_analyses        — AI 分析记录
reports            — 测试报告（无 project_id）
scenes             — 测试场景（无 project_id）
scene_steps        — 场景步骤
projects           — 项目
test_modules       — 模块目录
requirement_docs   — 需求文本（新增）
function_cases     — 功能测试用例（新增）
```

---

## 项目文件结构

```
d:\Ai-test-assistant\
├── README.md
├── docs/                        ← 文档目录
│   ├── 00_PROJECT_CONTEXT.md
│   ├── 01_REQUIREMENTS.md
│   ├── 06_CURRENT_STATUS.md
│   ├── 07_CHANGELOG.md
│   ├── 08_AI_CODING_RULES.md
│   └── 09_ACCEPTANCE_CHECKLIST.md
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── core/                (config.py, database.py)
│   │   ├── models/              (10 个 ORM 模型)
│   │   ├── schemas/             (10 组 Pydantic Schema)
│   │   ├── routers/             (11 个路由模块)
│   │   ├── services/            (10 个 Service 模块)
│   │   ├── utils/               (file_writer, pytest_runner, parameter)
│   │   └── tests_generated/     (生成的测试代码)
│   └── requirements.txt
└── frontend/
    └── src/
        ├── pages/               (9 个页面组件)
        ├── components/          (ModuleTree 可复用组件)
        ├── api/                 (API 调用封装：case/project/module/requirement/functionCase/scene/parameterFile)
        └── services/            (Axios 实例)
```
