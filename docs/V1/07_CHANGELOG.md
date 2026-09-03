# V1 / 07 — 变更日志

> 本文件只保留 V1 历史变更。V2 实施记录写入 `../V2/02_DEVELOPMENT_RECORD.md`。

---

## [V1.8] — 第三阶段：真实接口串联与场景执行增强

**日期**：2026-05-02

### Added

**后端 — 场景模型增强**
- 增强 `Scene` 模型 — 新增 `project_id`、`module_id`、`status`、`is_deleted` 共 4 个字段
- 增强 `SceneStep` 模型 — 新增 `step_name`、`extract_rules_json`(JSON)、`request_override_json`(JSON)、`assertions_json`(JSON)、`enabled`、`is_deleted`、`updated_at` 共 7 个字段
- 场景和步骤删除改为软删除（`is_deleted=True`）
- `GET /scenes` 新增 5 个筛选参数：`project_id`、`module_id`、`include_children`、`keyword`、`status`
- `PUT /scenes/steps/{step_id}` — 步骤编辑接口（支持部分更新所有字段）
- `PUT /scenes/{scene_id}/steps/reorder` — 步骤排序接口
- `POST /scenes/{scene_id}/execute` 增加 scene 状态守卫和 enabled 过滤

**后端 — 执行结果表**
- 新增 `SceneRun` 模型（`scene_runs` 表，15 字段）— 保存场景级执行结果
- 新增 `SceneStepRun` 模型（`scene_step_runs` 表，18 字段）— 保存步骤级请求/响应/提取/断言
- 新增 `GET /scenes/runs` — 查询场景执行历史（支持 scene_id/project_id/status 筛选）
- 新增 `GET /scenes/runs/{run_id}` — 查询某次执行详情（含步骤明细）
- 新增 `GET /scenes/{scene_id}/runs` — 查询某场景的执行历史
- 新增 `services/scene_run_service.py` — 4 个只读查询函数

**后端 — 工具函数**
- 新增 `utils/variable_resolver.py` — 3 个函数：
  - `get_by_json_path` — 简单 JSONPath 取值（支持 `$.data.token` / `$.items[0].id` / `$`）
  - `extract_variables` — 从响应 JSON 批量提取变量
  - `replace_variables` — 递归替换 `${变量名}`（str/dict/list，类型保留，嵌套错误汇总）
- 新增 `utils/assertion_runner.py` — 1 个函数：
  - `run_assertions` — 支持 status_code eq + json_path eq/contains/exists/not_empty

**后端 — 真实串联执行**
- 新增 `services/scene_chain_service.py` — 真实接口串联执行服务：
  - `execute_scene_chain` — 主控流程：验证 → 创建 SceneRun → 逐步执行 → 失败停止 → 更新结果
  - `build_request_from_case` — 构造请求（api_case 数据 + request_override_json 合并 + 变量替换）
  - `execute_http_request` — httpx.request（timeout=15s，异常不崩溃）
- 新增 `POST /scenes/{scene_id}/run-chain` — 真实串联执行接口（不走 pytest）
- 支持从上一步 HTTP 响应中提取变量到 context
- 支持 `${变量名}` 在 url/headers/body 中自动替换
- 支持步骤级断言（assertions_json），2xx 默认通过
- 任一步骤 failed/error → 后续步骤标记 skipped
- 每一步请求/响应/提取变量/断言结果写入 scene_step_runs

**前端 — 串联执行**
- `ScenePage` 新增"串联执行"按钮（与旧"一键执行"并列）
- 新增串联执行结果 Modal（status Tag / 统计 / context / 步骤明细 Table）
- `api/scene.js` 新增 `runSceneChain` / `updateSceneStep` / `reorderSceneSteps`

**前端 — 步骤配置增强**
- `SceneStepPage` 新增表单支持 `step_name` / `enabled`(Switch) / JSON 配置 Collapse
- 新增步骤编辑 Modal（7 个字段，JSON 正确回填）
- 新增步骤上移/下移排序（调 reorder 接口）
- 表格列扩展至 10 列（含"已配置/未配置"Tag）
- JSON 字段输入校验（非法 JSON 阻止提交）

### Changed
- `backend/app/models/scene.py` — 增加 4 个字段
- `backend/app/models/scene_step.py` — 增加 7 个字段
- `backend/app/schemas/scene.py` — 扩展所有 Schema + 新增 SceneStepUpdate / ReorderSceneStepsRequest
- `backend/app/services/scene_service.py` — 筛选/软删除/步骤编辑/排序/execute 守卫
- `backend/app/routers/scene_router.py` — 筛选参数 + 5 个新端点
- `backend/app/main.py` — 注册 SceneRun / SceneStepRun 模型
- `frontend/src/pages/ScenePage.jsx` — 串联执行按钮 + 结果 Modal
- `frontend/src/pages/SceneStepPage.jsx` — 全面增强
- `frontend/src/api/scene.js` — 新增 3 个函数

### Preserved
- `backend/app/services/ai_service.py` — 零改动
- `backend/app/services/run_service.py` — 零改动
- `backend/app/services/analysis_service.py` — 零改动
- `backend/app/services/report_service.py` — 零改动
- `backend/app/utils/pytest_runner.py` — 零改动
- `backend/app/utils/file_writer.py` — 零改动
- `POST /scenes/{scene_id}/execute` — 保留旧 pytest 执行方式
- 所有第一/第二阶段页面 — 零改动

---

## [V1.7] — 第二阶段：需求文本管理与功能测试用例生成

**日期**：2026-05-01

### Added

**后端 — 需求文本管理**
- 新增 `RequirementDoc` 模型 + CRUD + 筛选
- 新增 `POST/GET/PUT/DELETE /requirements`

**后端 — 功能测试用例管理**
- 新增 `FunctionCase` 模型（18 字段，含 case_code / steps_json / test_data_json JSON 类型）
- 新增 `POST/GET/PUT/DELETE /function-cases` + 9 个筛选参数

**后端 — 需求生成功能测试用例**
- 新增 `POST /function-cases/generate-from-requirement` — LLM 生成预览
- 新增 `POST /function-cases/save-generated` — 保存勾选用例（source=llm）
- 复用 `ai_service.call_llm_generate_code` 不修改 ai_service.py

**前端**
- 新增 `RequirementPage` + `FunctionCasePage`
- `RequirementPage` 增加"生成用例"按钮 + 预览弹窗 + 勾选保存

### Preserved
- `ai_service.py` / `run_service.py` / `analysis_service.py` / `report_service.py` / `pytest_runner.py` / `file_writer.py` — 零改动

---

## [V1.6] — 第一阶段：项目管理 + 模块目录树 + 用例归类

**日期**：2026-05-01

### Added

**后端 — 项目管理** — `Project` 模型 + CRUD
**后端 — 模块目录树** — `TestModule` 模型 + 树查询 + 移动 + 排序
**后端 — api_cases 字段扩展** — +7 字段，+8 筛选参数，软删除
**前端** — `ProjectPage` + `ModuleTree` 组件 + `CasePage` 改造

### Preserved
- `ai_service.py` / `run_service.py` / `analysis_service.py` / `report_service.py` / `pytest_runner.py` / `file_writer.py` — 零改动

---

## [UNRELEASED] — 初始化文档

**日期**：2026-05-01

### Added
- 新建 `docs/` 目录，新增 6 个文档文件

---

## 历史版本（V1.0 ~ V1.5）

| 版本 | 内容概要 |
|------|---------|
| V1.0 | Demo 初始化：FastAPI + React，用例 CRUD，LLM/规则代码生成，pytest 执行 |
| V1.1 | README 更新 |
| V1.2 | 参数管理模块 |
| V1.3 | 场景管理模块 |
| V1.4 | AI 分析模块 |
| V1.5 | 报告模块 |
