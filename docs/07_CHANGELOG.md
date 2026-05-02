# 07 — 变更日志

---

## [V1.7] — 第二阶段：需求文本管理与功能测试用例生成

**日期**：2026-05-02

### Added

**后端 — 需求文本管理**
- 新增 `backend/app/models/requirement_doc.py` — RequirementDoc ORM 模型（`requirement_docs` 表）
- 新增 `backend/app/schemas/requirement_doc.py` — RequirementDocCreate / Update / Response
- 新增 `backend/app/services/requirement_doc_service.py` — 需求 CRUD + 6 个筛选参数（project_id / module_id / include_children / keyword / status / requirement_type）
- 新增 `backend/app/routers/requirement_doc_router.py` — `POST/GET/PUT/DELETE /requirements` 共 5 个接口

**后端 — 功能测试用例管理**
- 新增 `backend/app/models/function_case.py` — FunctionCase ORM 模型（`function_cases` 表，18 个字段）
  - 包含 `case_code` 用例编号字段
  - `steps_json` 和 `test_data_json` 使用 SQLAlchemy JSON 类型
- 新增 `backend/app/schemas/function_case.py` — FunctionCaseCreate / Update / Response
- 新增 `backend/app/services/function_case_service.py` — 功能用例 CRUD + 9 个筛选参数
- 新增 `backend/app/routers/function_case_router.py` — `POST/GET/PUT/DELETE /function-cases` 共 5 个接口

**后端 — 需求生成功能测试用例**
- 新增 `backend/app/schemas/function_case_generation.py` — 5 个 Schema（GenerateRequest / GeneratedItem / GenerateResponse / SaveRequest / SaveResponse）
- 新增 `backend/app/services/function_case_generation_service.py` — Prompt 构建、3 级 JSON 解析回退、字段校验、LLM 生成、批量保存
- 新增 `POST /function-cases/generate-from-requirement` — 根据需求文本调用 LLM 生成功能用例预览（不写表）
- 新增 `POST /function-cases/save-generated` — 保存勾选的生成用例（project_id 以后端查询为准，source 固定 llm）
- 复用 `ai_service.call_llm_generate_code()` — 不修改 ai_service.py，仅调用已有函数

**前端 — 需求文本管理页面**
- 新增 `frontend/src/api/requirement.js` — 需求文本 API 封装
- 新增 `frontend/src/pages/RequirementPage.jsx` — 项目选择、模块树筛选、keyword/status/type 筛选、CRUD、详情弹窗
- `App.jsx` 导航增加"需求管理"入口

**前端 — 功能测试用例管理页面**
- 新增 `frontend/src/api/functionCase.js` — 功能测试用例 API 封装 + 生成接口封装
- 新增 `frontend/src/pages/FunctionCasePage.jsx` — 项目选择、模块树筛选、需求筛选、多条件筛选、JSON 字段解析/回填、查看详情
- `App.jsx` 导航增加"功能用例"入口

**前端 — RequirementPage "生成用例"按钮**
- 操作列增加"生成用例"按钮 → 调 LLM 生成接口 → 预览弹窗（Table + rowSelection）
- 支持勾选部分生成结果 → 批量保存
- 保存后 `source=llm`，可在 FunctionCasePage 查看

### Changed
- `backend/app/main.py` — 注册 RequirementDoc 和 FunctionCase 模型及路由
- `backend/app/models/__init__.py` — 追加 RequirementDoc, FunctionCase
- `backend/app/routers/__init__.py` — 追加 requirement_doc_router, function_case_router
- `backend/app/schemas/__init__.py` — 追加 RequirementDoc 和 FunctionCase Schema
- `backend/app/routers/function_case_router.py` — 追加 2 个生成端点
- `frontend/src/App.jsx` — 增加"需求管理"和"功能用例"导航入口
- `frontend/src/pages/RequirementPage.jsx` — 追加"生成用例"按钮和预览弹窗
- `frontend/src/api/functionCase.js` — 追加 2 个生成 API 函数

### Preserved
- `backend/app/services/ai_service.py` — 零修改（仅调用 `call_llm_generate_code`）
- `backend/app/services/run_service.py` — 零修改
- `backend/app/services/analysis_service.py` — 零修改
- `backend/app/services/report_service.py` — 零修改
- `backend/app/utils/pytest_runner.py` — 零修改
- `backend/app/utils/file_writer.py` — 零修改
- 所有第一阶段页面（ProjectPage, CasePage, ModuleTree）— 零修改
- 所有原有页面（RunPage, ScenePage, SceneStepPage, ReportPage, ParameterPage）— 零修改

---

## [V1.6] — 第一阶段：项目管理 + 模块目录树 + 用例归类

**日期**：2026-05-01

### Added

**后端 — 项目管理**
- 新增 `backend/app/models/project.py` — Project ORM 模型（`projects` 表）
- 新增 `backend/app/schemas/project.py` — ProjectCreate / ProjectUpdate / ProjectResponse
- 新增 `backend/app/services/project_service.py` — 项目 CRUD 业务逻辑
- 新增 `backend/app/routers/project_router.py` — `POST/GET/PUT/DELETE /projects` 共 5 个接口
- 支持 keyword 模糊搜索、status 筛选、软删除

**后端 — 模块目录树**
- 新增 `backend/app/models/test_module.py` — TestModule ORM 模型（`test_modules` 表）
- 新增 `backend/app/schemas/test_module.py` — Create / Update / Response / TreeResponse / MoveRequest / ReorderRequest
- 新增 `backend/app/services/test_module_service.py` — 模块树 CRUD + 移动 + 排序 + 子节点查询
- 新增 `backend/app/routers/module_router.py` — `POST /modules`, `GET /modules/tree`, `GET/PUT/DELETE /modules/{id}`, `PUT /modules/{id}/move`, `PUT /modules/reorder` 共 7 个接口
- 支持多级树形结构、同级排序、空模块软删除、模块移动

**后端 — api_cases 字段扩展**
- `api_cases` 表新增 7 个字段：`project_id`, `module_id`, `case_type`, `source`, `priority`, `status`, `is_deleted`
- `GET /cases` 新增 8 个筛选参数：`project_id`, `module_id`, `include_children`, `keyword`, `case_type`, `source`, `priority`, `status`
- `DELETE /cases/{id}` 从物理删除改为软删除

**前端 — 项目管理页面**
- 新增 `frontend/src/api/project.js` — 项目管理 API 封装
- 新增 `frontend/src/pages/ProjectPage.jsx` — 项目列表、新增、编辑、删除、keyword 搜索、status 筛选
- `App.jsx` 导航增加"项目管理"入口

**前端 — 模块目录树组件**
- 新增 `frontend/src/api/module.js` — 模块目录 API 封装
- 新增 `frontend/src/components/ModuleTree.jsx` — 可复用模块树组件
- 支持树展示、新增一级/子模块、编辑、删除空模块、同级上移/下移排序

**前端 — CasePage 接入项目与模块**
- 顶部增加项目选择 Select
- 左侧接入 ModuleTree 组件 + "包含子模块" Checkbox
- 右侧用例列表按 project_id / module_id / include_children 筛选
- 新增/编辑表单支持 project_id, module_id, case_type, source, priority, status
- 表格新增 6 列：项目ID、模块ID、类型、来源、优先级、状态

### Changed
- `backend/app/models/api_case.py` — 增加 7 个字段
- `backend/app/schemas/api_case.py` — APICaseCreate/Response 增加字段，APICaseUpdate 独立定义（全部可选）
- `backend/app/services/case_service.py` — 全部 5 个函数适配新字段 + 筛选 + 软删除
- `backend/app/routers/case_router.py` — GET /cases 增加 8 个 Query 参数
- `backend/app/main.py` — 注册 Project 和 TestModule 模型及路由
- `backend/app/models/__init__.py` — 追加 Project, TestModule
- `backend/app/routers/__init__.py` — 追加 project_router, module_router
- `backend/app/schemas/__init__.py` — 追加 Project 和 TestModule Schema
- `frontend/src/pages/CasePage.jsx` — 布局和表单改造
- `frontend/src/App.jsx` — 增加项目管理入口

### Preserved
- `backend/app/services/ai_service.py` — 零改动
- `backend/app/services/run_service.py` — 零改动
- `backend/app/services/analysis_service.py` — 零改动
- `backend/app/services/report_service.py` — 零改动
- `backend/app/utils/pytest_runner.py` — 零改动
- `backend/app/utils/file_writer.py` — 零改动
- 所有已有前端页面（RunPage, ScenePage, SceneStepPage, ReportPage, ParameterPage）— 零改动

---

## [UNRELEASED] — 初始化文档

**日期**：2026-05-01

### Added
- 新增 `docs/00_PROJECT_CONTEXT.md` — 项目上下文文档
- 新增 `docs/01_REQUIREMENTS.md` — 需求规格文档
- 新增 `docs/06_CURRENT_STATUS.md` — 当前状态文档
- 新增 `docs/07_CHANGELOG.md` — 变更日志文档（本文件）
- 新增 `docs/08_AI_CODING_RULES.md` — AI 编码规则文档
- 新增 `docs/09_ACCEPTANCE_CHECKLIST.md` — 验收清单文档
- 新建 `docs/` 目录作为项目文档根目录

### Changed
- 无业务代码变更

---

## 版本记录规则

后续每次功能迭代，在本文件中按以下格式记录：

```markdown
## [VX.Y] — 简短标题

**日期**：YYYY-MM-DD

### Added
- 新增的功能

### Changed
- 修改的功能

### Fixed
- 修复的问题

### Deprecated
- 即将废弃的功能
```

---

## 历史版本（V1.0 ~ V1.5）

以下为文档建设之前的版本记录（基于 git log 回溯）：

| 版本 | Git Commit | 内容概要 |
|------|-----------|---------|
| V1.0 | `cad202f` ~ `37b2756` | Demo 初始化：FastAPI + React 框架搭建，用例 CRUD，LLM/规则代码生成，pytest 执行 |
| V1.1 | `7cfe88d` | README 更新 |
| V1.2 | `922e263` | 参数管理模块（parameter.py 在线编辑） |
| V1.3 | `ead52ef` | 场景管理模块（场景 CRUD + 步骤管理 + 场景执行） |
| V1.4 | `e8a9f32` | AI 分析模块（失败根因分析） |
| V1.5 | `6e2589d` | 报告模块（项目级测试报告生成） |
