# V1 / 06 — 最终状态快照

> 历史快照：用于 V2 回归基线，不代表当前 V2 开发状态。

> 更新日期：2026-05-02

## 当前阶段

**第三阶段已完成，项目核心功能基本完成** — 准备进入收尾优化、报告增强、登录权限、论文材料整理阶段。

---

## 一、第三阶段已完成内容

**第三阶段名称：「真实接口串联与场景执行增强」**

### 1.1 后端 — 场景模型增强

| 任务 | 内容 | 关键文件 |
|------|------|---------|
| Scene 表增强 | 新增 `project_id`、`module_id`、`status`、`is_deleted` 共 4 个字段；软删除 | `models/scene.py` |
| SceneStep 表增强 | 新增 `step_name`、`extract_rules_json`(JSON)、`request_override_json`(JSON)、`assertions_json`(JSON)、`enabled`、`is_deleted`、`updated_at` 共 7 个字段；软删除 | `models/scene_step.py` |
| 场景筛选 | GET /scenes 支持 `project_id`、`module_id`、`include_children`、`keyword`、`status` 共 5 个筛选参数 | `services/scene_service.py` |
| 步骤编辑 | PUT /scenes/steps/{step_id} 支持部分更新所有字段 | `services/scene_service.py`, `routers/scene_router.py` |
| 步骤排序 | PUT /scenes/{scene_id}/steps/reorder 接收 ordered_step_ids 批量更新 step_order | `services/scene_service.py`, `routers/scene_router.py` |
| execute 守卫 | 旧执行接口增加 scene 状态校验（is_deleted=False, status=active）+ enabled 过滤 | `services/scene_service.py` |

### 1.2 后端 — 执行结果表与查询

| 任务 | 内容 | 关键文件 |
|------|------|---------|
| SceneRun 表 | 15 个字段：scene_id, project_id, module_id, status, total/passed/failed/skipped_steps, context_json, error_message, started/finished_at, duration_ms | `models/scene_run.py` |
| SceneStepRun 表 | 18 个字段：请求/响应/提取变量/断言结果全部落库 | `models/scene_step_run.py` |
| 结果查询 | GET /scenes/runs, GET /scenes/runs/{run_id}, GET /scenes/{scene_id}/runs | `services/scene_run_service.py`, `routers/scene_router.py` |

### 1.3 后端 — 工具函数

| 任务 | 内容 | 关键文件 |
|------|------|---------|
| 变量替换工具 | `get_by_json_path` / `extract_variables` / `replace_variables` — JSONPath 取值、变量提取、`${变量名}` 递归替换 | `utils/variable_resolver.py` |
| 断言工具 | `run_assertions` — 支持 status_code eq / json_path eq+contains+exists+not_empty | `utils/assertion_runner.py` |

### 1.4 后端 — 真实串联执行

| 任务 | 内容 | 关键文件 |
|------|------|---------|
| 串联执行服务 | `execute_scene_chain` — httpx 顺序请求、变量提取与替换、断言、结果落库、失败停止+跳过 | `services/scene_chain_service.py` |
| 串联执行接口 | POST /scenes/{scene_id}/run-chain — 真实串联执行入口 | `routers/scene_router.py` |
| 请求构造 | `build_request_from_case` — api_case + request_override_json + 变量替换 | `services/scene_chain_service.py` |

### 1.5 前端

| 任务 | 内容 | 关键文件 |
|------|------|---------|
| ScenePage 串联执行 | 新增"串联执行"按钮 + 串联执行结果 Modal（status/统计/context/步骤明细） | `pages/ScenePage.jsx`, `api/scene.js` |
| SceneStepPage 增强 | 新增表单支持 step_name/enabled/JSON 配置；编辑 Modal；上移/下移排序；表格列扩展 | `pages/SceneStepPage.jsx`, `api/scene.js` |

### 1.6 保留的核心链路（零改动）

以下 6 个文件在第三阶段**仍未修改**：

| 文件 | 承载的链路 | 第三阶段做法 |
|------|-----------|------------|
| `ai_service.py` | LLM 代码生成 + 规则生成 | 未修改 |
| `run_service.py` | 测试执行编排 | 串行执行改用 httpx，不调 run_service |
| `analysis_service.py` | AI 失败分析 | 未修改 |
| `report_service.py` | 项目报告生成 | 未修改 |
| `pytest_runner.py` | pytest subprocess | 串行执行不走 pytest |
| `file_writer.py` | 测试代码落盘 | 未修改 |

---

## 二、第三阶段明确未做

1. 不生成场景 pytest 代码
2. 不做 UI 自动化
3. 不做复杂条件分支
4. 不做循环场景
5. 不做并发执行
6. 不做 AI 自动生成场景
7. 不做复杂 JSONPath（通配符/过滤器）
8. 不做拖拽排序
9. 不做登录权限
10. 不做报告图表增强

---

## 三、下一阶段目标

**第四阶段：「系统收尾优化与论文材料准备」**

计划内容：
1. 报告按项目和模块统计增强
2. 登录和权限管理
3. 前端统一优化
4. 演示数据准备
5. 系统截图整理
6. 论文实验章节准备
7. 答辩演示流程准备

---

## 功能清单（第三阶段完成后 = 项目核心功能全景）

| 功能模块 | 状态 | 关键文件 |
|---------|------|---------|
| 项目管理 | ✅ | `routers/project_router.py` |
| 模块目录树 | ✅ | `routers/module_router.py` |
| 接口测试用例 CRUD | ✅ | `routers/case_router.py` |
| LLM 生成 pytest | ✅ | `services/ai_service.py` |
| 规则生成 pytest | ✅ | `services/ai_service.py` |
| pytest 执行 | ✅ | `services/run_service.py`, `utils/pytest_runner.py` |
| AI 失败分析 | ✅ | `services/analysis_service.py` |
| 需求文本管理 | ✅ | `routers/requirement_doc_router.py` |
| 需求生成功能用例 | ✅ | `services/function_case_generation_service.py` |
| 功能测试用例管理 | ✅ | `routers/function_case_router.py` |
| 场景管理 | ✅ | `routers/scene_router.py` |
| 场景步骤配置 | ✅ | `routers/scene_router.py` |
| 真实接口串联执行 | ✅ | `services/scene_chain_service.py` |
| 变量提取与替换 | ✅ | `utils/variable_resolver.py` |
| 轻量断言 | ✅ | `utils/assertion_runner.py` |
| 场景执行结果记录 | ✅ | `models/scene_run.py`, `models/scene_step_run.py` |
| 报告生成 | ✅ | `services/report_service.py` |
| 参数管理 | ✅ | `routers/parameter_file_router.py` |
| 前端 9 页面 | ✅ | `frontend/src/pages/*.jsx` |

---

## 数据库当前状态

SQLite 单文件 `ai_test_assistant.db`，**12 张表**：

```
api_cases          — 接口测试用例
test_runs          — 执行记录（单用例 pytest 执行）
ai_analyses        — AI 分析记录
reports            — 测试报告
scenes             — 测试场景（已增加 project_id/module_id/status/is_deleted）
scene_steps        — 场景步骤（已增加 step_name/extract/request_override/assertions/enabled/is_deleted）
scene_runs         — 场景执行结果（新增）
scene_step_runs    — 场景步骤执行结果（新增）
projects           — 项目
test_modules       — 模块目录
requirement_docs   — 需求文本
function_cases     — 功能测试用例
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
│   │   ├── models/              (12 个 ORM 模型)
│   │   ├── schemas/             (12 组 Pydantic Schema)
│   │   ├── routers/             (12 个路由模块)
│   │   ├── services/            (12 个 Service 模块)
│   │   ├── utils/               (variable_resolver, assertion_runner, pytest_runner, file_writer, parameter)
│   │   └── tests_generated/     (生成的 pytest 代码)
│   └── requirements.txt
└── frontend/
    └── src/
        ├── pages/               (9 个页面组件)
        ├── components/          (ModuleTree)
        ├── api/                 (6 组 API 封装)
        └── services/            (Axios 实例)
```
