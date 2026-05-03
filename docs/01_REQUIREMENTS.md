# 01 — 需求规格

## 项目名称

**基于大语言模型的测试管理平台**

---

## 版本规划总览

| 阶段 | 名称 | 状态 |
|------|------|------|
| V1.0 ~ V1.5 | Demo 闭环 | ✅ 已完成 |
| **第一阶段** | 项目管理 + 模块目录树 + 用例按项目/模块分类 | ✅ 已完成 |
| **第二阶段** | 需求文本管理 + 功能测试用例管理 + 需求生成测试用例 | ✅ 已完成 |
| **第三阶段** | 真实接口串联与场景执行增强 | ✅ 已完成 |
| 第四阶段 | 系统收尾优化与论文材料准备 | 📋 规划中 |

---

## 已完成功能

### 项目管理

- [x] 创建、编辑、删除、查询项目
- [x] 项目名称、描述、状态管理
- [x] 前端项目选择与切换
- [x] 软删除支持

### 模块目录管理

- [x] 多级模块目录树
- [x] 模块增删改查 + 同级排序（上移/下移/reorder）
- [x] 前端 ModuleTree 可复用组件
- [x] 仅允许删除空模块（无子模块）

### 接口测试用例管理

- [x] API 用例 CRUD
- [x] 按项目、模块、来源、优先级、状态筛选
- [x] keyword 搜索 + include_children 子模块查询
- [x] 软删除

### AI 生成 pytest

- [x] LLM 生成 pytest 接口测试代码
- [x] 规则生成 pytest 代码（确定性）
- [x] pytest subprocess 执行 + 响应采集
- [x] AI 失败分析

### 需求文本管理

- [x] 需求文本 CRUD + 软删除
- [x] 按项目、模块、状态、类型筛选
- [x] 前端 RequirementPage

### 功能测试用例管理

- [x] 功能测试用例 CRUD（18 字段，含 case_code / steps_json / test_data_json）
- [x] 按项目、模块、需求、来源、优先级、状态筛选
- [x] 前端 FunctionCasePage + JSON 字段处理

### 需求生成功能测试用例

- [x] POST /function-cases/generate-from-requirement — LLM 生成预览
- [x] POST /function-cases/save-generated — 勾选保存
- [x] 保存后 source=llm
- [x] 复用 ai_service.call_llm_generate_code

### 场景管理

- [x] 场景 CRUD + 按项目/模块/状态筛选
- [x] 场景步骤管理（增删改 + 排序）
- [x] 步骤配置：step_name / extract_rules / request_override / assertions / enabled
- [x] 软删除

### 真实接口串联执行

- [x] POST /scenes/{scene_id}/run-chain — httpx 串联执行
- [x] 变量提取（get_by_json_path / extract_variables）
- [x] 变量替换（replace_variables — `${变量名}` 递归替换 + 类型保留）
- [x] 轻量断言（status_code eq / json_path eq+contains+exists+not_empty）
- [x] 失败停止 + 后续 skipped
- [x] 结果写入 scene_runs + scene_step_runs

### 场景执行结果记录

- [x] SceneRun 表（15 字段）
- [x] SceneStepRun 表（18 字段）
- [x] 执行历史查询接口

### 测试报告

- [x] 项目级测试报告生成

### 参数管理

- [x] parameter.py 在线编辑

### 前端

- [x] 9 个页面：CasePage / ProjectPage / RequirementPage / FunctionCasePage / ScenePage / SceneStepPage / RunPage / ReportPage / ParameterPage
- [x] 1 个可复用组件：ModuleTree

---

## 待完成或可优化

| 功能 | 优先级 |
|------|--------|
| 报告按项目/模块统计图表增强 | 中 |
| 用户登录与权限管理 | 中 |
| 前端 UI 统一优化 | 低 |
| 演示数据准备 | 高（论文） |
| 论文实验数据整理 | 高（论文） |
| 答辩演示流程准备 | 高（论文） |

---

## 非功能需求

- 后端 API 响应时间 < 5s（LLM 调用除外）
- LLM 调用超时时间 60s
- httpx 串联执行超时 15s
- 前端页面首屏加载 < 3s
- SQLite 单文件数据库，无需独立部署
- 支持 Windows / macOS 本地开发运行
