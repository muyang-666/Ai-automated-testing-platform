# 06 — 当前状态

> 更新日期：2026-05-01

## 当前阶段

**第一阶段改造前准备** — 文档建设与方案设计阶段。

当前已完成 V1.5 Demo，具备完整的单接口自动化测试闭环。在开始编码改造之前，先完成项目文档建设，明确改造目标和约束。

---

## 一、第一阶段范围

**第一阶段名称：「项目管理 + 模块目录树 + 接口测试用例按项目/模块分类」**

### 第一阶段只做

1. 新增项目管理（`projects` 表 + CRUD 接口 + 前端页面）
2. 新增模块目录树（`modules` 表 + 多级树形结构 + CRUD 接口 + 前端树形组件）
3. 给现有 `api_cases` 表增加以下字段：
   - `project_id` — 归属项目（必填，外键）
   - `module_id` — 归属模块（可选，外键）
   - `case_type` — 用例类型（默认 `api`）
   - `source` — 用例来源（默认 `manual`）
   - `priority` — 优先级（默认 `P2`）
   - `status` — 用例状态（默认 `draft`）
   - `is_deleted` — 软删除标记（默认 `false`）
4. 用例管理页支持按项目筛选
5. 用例管理页支持按模块筛选/浏览
6. 新建/编辑接口测试用例时可以选择项目和模块
7. 保留原有用例 CRUD、AI 生成代码、规则生成代码、pytest 执行、AI 分析、场景管理、报告生成、参数管理能力

---

## 二、第一阶段暂不做

以下功能明确不在第一阶段范围，不允许以任何理由提前实现：

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

## 三、核心文件禁止修改规则

以下 6 个文件在第一阶段 **完全禁止修改**，不允许新增函数、不允许新增参数、不允许修改已有逻辑：

| 禁止修改的文件 | 承载的链路 | 禁止级别 |
|---------------|-----------|---------|
| `backend/app/services/ai_service.py` | LLM 代码生成引擎 + 规则生成引擎 | 🔴 完全禁止 |
| `backend/app/services/run_service.py` | 测试执行编排 | 🔴 完全禁止 |
| `backend/app/services/analysis_service.py` | AI 失败分析 | 🔴 完全禁止 |
| `backend/app/services/report_service.py` | 项目报告生成 | 🔴 完全禁止 |
| `backend/app/utils/pytest_runner.py` | pytest subprocess 执行器 | 🔴 完全禁止 |
| `backend/app/utils/file_writer.py` | 测试代码文件落盘 | 🔴 完全禁止 |

> **规则**：以上文件在第一阶段中一行代码都不能改。如改造过程中发现必须修改以上文件才能完成目标，则停止改造，重新设计方案，在不修改这些文件的前提下实现目标。

---

## 四、默认项目与默认模块规则

### 4.1 默认测试项目

1. 系统允许创建一个"默认测试项目"（名称可自定义，如"默认项目"）
2. 如果数据库重建（删除 `.db` 文件后重启），初始化后用户可手动创建默认测试项目
3. 旧 Demo 数据如果存在（`api_cases` 表中有存量数据），可临时归属到默认测试项目
4. 旧数据迁移策略：改造后首次启动时，若存在无 `project_id` 的用例，将其批量归属到默认测试项目

### 4.2 project_id 规则

1. 新增用例时 `project_id` **必须指定**（不允许为空）
2. 编辑用例时不允许将 `project_id` 置空

### 4.3 module_id 规则

1. `module_id` **可以为空**（null）
2. 如果用户没有选择模块，用例归属到"未分类"

### 4.4 默认模块（"未分类"）

1. 可以在每个项目下创建一个默认模块，名称为"未分类"
2. 默认模块不可删除
3. 默认模块的 `parent_id` 为 null（一级模块）
4. 第一阶段不强制所有用例必须有 `module_id`

---

## 五、模块删除规则

1. **仅允许删除空模块** — 模块下无子模块且无用例时才能删除
2. 如果模块下存在子模块，**不允许删除**（先删除子模块）
3. 如果模块下存在接口测试用例（含软删除用例），**不允许删除**（先将用例移走或删除）
4. **删除校验必须以后端为准** — 后端接口负责判断模块是否可删除
5. **前端只负责提示** — 前端根据后端返回的错误信息提示用户，不作为最终判断
6. **第一阶段不做级联删除** — 删除模块时不会自动删除子模块或用例

---

## 六、模块排序规则

1. 第一阶段支持**同级排序**（同一父模块下的子模块之间排序）
2. 可以通过上移/下移操作调整 `sort_order` 字段值
3. 可提供 `POST /modules/reorder` 接口接收排序后的模块 ID 列表，后端批量更新 `sort_order`
4. 第一阶段**不强制实现跨父模块拖拽**（如将模块从父模块 A 拖到父模块 B）
5. 如果实现 `POST /modules/{id}/move` 接口（更改父模块），只作为后端能力保留，前端可暂不开放复杂拖拽交互

---

## V1.5 已有功能清单

| 功能模块 | 状态 | 关键文件 |
|---------|------|---------|
| 用例 CRUD | ✅ 正常 | `routers/case_router.py`, `services/case_service.py` |
| LLM 生成测试代码 | ✅ 正常 | `routers/ai_router.py`, `services/ai_service.py` |
| 规则生成测试代码 | ✅ 正常 | `routers/ai_router.py`, `services/ai_service.py` |
| pytest 执行 | ✅ 正常 | `routers/run_router.py`, `services/run_service.py`, `utils/pytest_runner.py` |
| 响应采集 | ✅ 正常 | `utils/pytest_runner.py` |
| AI 失败分析 | ✅ 正常 | `routers/ai_router.py`, `services/analysis_service.py` |
| 场景管理 | ✅ 正常 | `routers/scene_router.py`, `services/scene_service.py` |
| 场景执行 | ✅ 正常 | `services/scene_service.py` |
| 报告生成 | ✅ 正常 | `routers/report_router.py`, `services/report_service.py` |
| 参数管理 | ✅ 正常 | `routers/parameter_file_router.py`, `utils/parameter.py` |
| 前端 6 页面 | ✅ 正常 | `frontend/src/pages/*.jsx` |

## 当前数据模型局限

| 问题 | 影响 | 改造方向 |
|------|------|---------|
| 无项目管理概念 | 所有数据平铺，无法区分不同项目 | 新增 projects 表 |
| 无用例分类/模块树 | 用例无法按功能模块组织 | 新增 modules 表 + 树结构 |
| 场景与报告无项目归属 | 多项目场景混在一起 | 后续阶段增加 project_id 外键 |
| 无功能测试用例 | 仅支持接口用例 | 后续阶段新增功能用例模型 |
| 无需求文本管理 | AI 生成用例缺乏上下文 | 后续阶段新增需求文本模型 |

## 数据库当前状态

SQLite 单文件 `ai_test_assistant.db`，6 张表：

```
api_cases     — 测试用例（无 project_id / module_id / case_type / source / priority / status / is_deleted）
test_runs     — 执行记录
ai_analyses   — AI 分析记录
reports       — 测试报告（无 project_id）
scenes        — 测试场景（无 project_id）
scene_steps   — 场景步骤
```

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
│   │   ├── models/              (6 个 ORM 模型)
│   │   ├── schemas/             (6 组 Pydantic Schema)
│   │   ├── routers/             (7 个路由模块)
│   │   ├── services/            (6 个 Service 模块)
│   │   ├── utils/               (file_writer, pytest_runner, parameter)
│   │   └── tests_generated/     (生成的测试代码)
│   └── requirements.txt
└── frontend/
    └── src/
        ├── pages/               (6 个页面组件)
        ├── api/                 (API 调用封装)
        └── services/            (Axios 实例)
```
