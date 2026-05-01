# 06 — 当前状态

> 更新日期：2026-05-01

## 当前阶段

**第一阶段已完成，准备进入第二阶段** — 需求文本管理 + 功能测试用例管理。

---

## 一、第一阶段已完成内容

**第一阶段名称：「项目管理 + 模块目录树 + 接口测试用例按项目/模块分类」**

### 1.1 后端

| 任务 | 内容 | 关键文件 |
|------|------|---------|
| Project CRUD | `projects` 表 + 5 个 REST 接口（增/查列表/查详情/改/软删除） | `models/project.py`, `schemas/project.py`, `services/project_service.py`, `routers/project_router.py` |
| TestModule CRUD + Tree | `test_modules` 表 + 7 个 REST 接口（增/树查询/详情/改/软删除/移动/排序） | `models/test_module.py`, `schemas/test_module.py`, `services/test_module_service.py`, `routers/module_router.py` |
| api_cases 字段扩展 | 新增 `project_id`, `module_id`, `case_type`, `source`, `priority`, `status`, `is_deleted` 共 7 个字段 | `models/api_case.py` |
| /cases 筛选增强 | GET /cases 支持 `project_id`, `module_id`, `include_children`, `keyword`, `case_type`, `source`, `priority`, `status` 共 8 个筛选参数 | `services/case_service.py`, `routers/case_router.py` |
| 用例软删除 | DELETE /cases/{id} 从物理删除改为软删除（`is_deleted = True`） | `services/case_service.py` |
| 主入口注册 | 在 `main.py` 注册 Project 和 Module 模型及路由 | `main.py` |

### 1.2 前端

| 任务 | 内容 | 关键文件 |
|------|------|---------|
| ProjectPage | 项目管理页面：项目列表、新增、编辑、删除、keyword 搜索、status 筛选 | `pages/ProjectPage.jsx`, `api/project.js` |
| ModuleTree 组件 | 可复用模块目录树组件：树展示、新增一级/子模块、编辑、删除空模块、同级上移/下移排序 | `components/ModuleTree.jsx`, `api/module.js` |
| CasePage 改造 | 接入项目选择 + ModuleTree 筛选 + 新增/编辑表单支持新字段（project_id/module_id/case_type/source/priority/status） | `pages/CasePage.jsx` |
| 导航更新 | App.jsx 增加"项目管理"入口 | `App.jsx` |

### 1.3 保留的核心链路（零改动）

以下 6 个核心文件在整个第一阶段**一行未改**：

| 文件 | 承载的链路 |
|------|-----------|
| `backend/app/services/ai_service.py` | LLM 代码生成 + 规则生成 |
| `backend/app/services/run_service.py` | 测试执行编排 |
| `backend/app/services/analysis_service.py` | AI 失败分析 |
| `backend/app/services/report_service.py` | 项目报告生成 |
| `backend/app/utils/pytest_runner.py` | pytest subprocess 执行器 |
| `backend/app/utils/file_writer.py` | 测试代码文件落盘 |

---

## 二、第一阶段未做（延后到后续阶段）

以下功能明确不在第一阶段范围，未实现：

1. 需求文本管理
2. 功能测试用例管理
3. 功能测试用例生成
4. 用户登录注册
5. 权限管理
6. 场景管理按项目过滤
7. 报告按项目过滤
8. 生成代码目录按项目/模块拆分
9. MySQL 切换
10. 多环境管理
11. 接口信息和接口用例彻底拆分

---

## 三、下一阶段目标

**第二阶段：「需求文本管理 + 功能测试用例管理」**

计划内容：
1. 新增需求文本管理（`requirements` 表 + CRUD 接口 + 前端页面）
2. 新增功能测试用例管理（`functional_cases` 表 + CRUD 接口 + 前端页面）
3. 基于需求文本，LLM 生成功能测试用例
4. 保留第一阶段所有能力

---

## 四、核心文件禁止修改规则（延续至后续阶段）

以下 6 个文件在后续阶段仍**禁止修改**，除非明确解禁：

| 禁止修改的文件 | 承载的链路 | 禁止级别 |
|---------------|-----------|---------|
| `backend/app/services/ai_service.py` | LLM 代码生成引擎 + 规则生成引擎 | 🔴 完全禁止 |
| `backend/app/services/run_service.py` | 测试执行编排 | 🔴 完全禁止 |
| `backend/app/services/analysis_service.py` | AI 失败分析 | 🔴 完全禁止 |
| `backend/app/services/report_service.py` | 项目报告生成 | 🔴 完全禁止 |
| `backend/app/utils/pytest_runner.py` | pytest subprocess 执行器 | 🔴 完全禁止 |
| `backend/app/utils/file_writer.py` | 测试代码文件落盘 | 🔴 完全禁止 |

> **规则**：以上文件在后续阶段中一行代码都不能改。如改造过程中发现必须修改以上文件才能完成目标，则停止改造，重新设计方案。

---

## V1.5 已有功能清单（第一阶段改造后全部保留）

| 功能模块 | 状态 | 关键文件 |
|---------|------|---------|
| 用例 CRUD | ✅ 正常（已增强：支持项目/模块筛选 + 新字段） | `routers/case_router.py`, `services/case_service.py` |
| LLM 生成测试代码 | ✅ 正常 | `routers/ai_router.py`, `services/ai_service.py` |
| 规则生成测试代码 | ✅ 正常 | `routers/ai_router.py`, `services/ai_service.py` |
| pytest 执行 | ✅ 正常 | `routers/run_router.py`, `services/run_service.py`, `utils/pytest_runner.py` |
| 响应采集 | ✅ 正常 | `utils/pytest_runner.py` |
| AI 失败分析 | ✅ 正常 | `routers/ai_router.py`, `services/analysis_service.py` |
| 场景管理 | ✅ 正常 | `routers/scene_router.py`, `services/scene_service.py` |
| 场景执行 | ✅ 正常 | `services/scene_service.py` |
| 报告生成 | ✅ 正常 | `routers/report_router.py`, `services/report_service.py` |
| 参数管理 | ✅ 正常 | `routers/parameter_file_router.py`, `utils/parameter.py` |
| 项目管理 | ✅ 新增 | `routers/project_router.py`, `services/project_service.py` |
| 模块目录树 | ✅ 新增 | `routers/module_router.py`, `services/test_module_service.py` |
| 前端 7 页面 | ✅ 正常（新增 ProjectPage） | `frontend/src/pages/*.jsx` |

---

## 数据库当前状态

SQLite 单文件 `ai_test_assistant.db`，8 张表：

```
api_cases     — 测试用例（已增加 project_id / module_id / case_type / source / priority / status / is_deleted）
test_runs     — 执行记录
ai_analyses   — AI 分析记录
reports       — 测试报告（无 project_id）
scenes        — 测试场景（无 project_id）
scene_steps   — 场景步骤
projects      — 项目（新增）
test_modules  — 模块目录（新增）
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
│   │   ├── models/              (8 个 ORM 模型：含 project 和 test_module)
│   │   ├── schemas/             (8 组 Pydantic Schema)
│   │   ├── routers/             (9 个路由模块)
│   │   ├── services/            (8 个 Service 模块)
│   │   ├── utils/               (file_writer, pytest_runner, parameter)
│   │   └── tests_generated/     (生成的测试代码)
│   └── requirements.txt
└── frontend/
    └── src/
        ├── pages/               (7 个页面组件：含 ProjectPage)
        ├── components/          (ModuleTree 可复用组件)
        ├── api/                 (API 调用封装：case/project/module/scene/parameterFile)
        └── services/            (Axios 实例)
```
