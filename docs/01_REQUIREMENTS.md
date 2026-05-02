# 01 — 需求规格

## 项目名称

**基于大语言模型的测试管理平台**

---

## 版本规划总览

| 阶段 | 名称 | 状态 |
|------|------|------|
| V1.0 ~ V1.5 | Demo 闭环（用例管理 → LLM生成 → 执行 → 分析 → 报告） | ✅ 已完成 |
| **第一阶段** | **项目管理 + 模块目录树 + 用例按项目/模块分类** | ✅ 已完成 |
| **第二阶段** | **需求文本管理 + 功能测试用例管理 + 需求生成测试用例** | ✅ 已完成 |
| 第三阶段 | 真实接口串联与场景执行增强 | 📋 规划中 |
| 后续阶段 | 报告增强、用户登录与权限、前端统一优化 | 📋 规划中 |

---

## 第一阶段功能（✅ 已完成）

### 1. 项目管理

- [x] 支持创建、编辑、删除、查询项目
- [x] 每个项目包含名称、描述、创建时间等基本信息
- [x] 用例归属到具体项目（`project_id` 必填）
- [x] 前端支持项目切换（CasePage / RequirementPage / FunctionCasePage）
- [x] 支持创建"默认测试项目"
- [x] 软删除支持

### 2. 模块目录管理

- [x] 项目下支持多级模块目录树
- [x] 模块包含名称、父模块引用（`parent_id`）、排序序号（`sort_order`）
- [x] 支持模块的增删改查
- [x] 支持同级模块排序（上移/下移/reorder）
- [x] 用例可挂载到具体模块节点（`module_id` 可选）
- [x] 仅允许删除空模块（无子模块），不做级联删除
- [x] 前端 ModuleTree 可复用组件

### 3. 接口测试用例管理（增强）

- [x] 已有能力保留：API 用例的 CRUD
- [x] 用例字段扩展：新增 `project_id`、`module_id`、`case_type`、`source`、`priority`、`status`、`is_deleted`
- [x] 支持按项目筛选
- [x] 支持按模块筛选/浏览
- [x] 新建/编辑用例时可选择项目和模块
- [x] 软删除支持

---

## 第二阶段功能（✅ 已完成）

### 4. 需求文本管理

- [x] 支持在项目/模块下添加需求描述文本
- [x] 需求文本字段：title、content、requirement_type、status、remark
- [x] 支持需求的增删改查 + 软删除
- [x] 支持按 project_id、module_id、include_children、keyword、status、requirement_type 筛选
- [x] 前端 RequirementPage：项目选择、模块树筛选、CRUD、详情弹窗

### 5. 功能测试用例管理

- [x] 在接口测试用例之外，新增功能测试用例管理
- [x] 功能测试用例字段：case_code、case_name、case_type、source、priority、precondition、steps_json、test_data_json、expected_result、status、remark
- [x] steps_json 和 test_data_json 使用 JSON 类型存储
- [x] 支持功能测试用例的 CRUD + 软删除
- [x] 支持按 project_id、module_id、include_children、requirement_id、keyword、case_type、source、priority、status 筛选
- [x] 前端 FunctionCasePage：项目选择、模块树、需求筛选、多条件筛选、JSON 字段处理、查看详情

### 6. 功能测试用例生成（LLM）

- [x] 基于需求文本 + LLM 生成功能测试用例
- [x] `POST /function-cases/generate-from-requirement` — 生成预览（不写表）
- [x] `POST /function-cases/save-generated` — 保存勾选用例（source=llm）
- [x] Prompt 要求严格 JSON 数组输出，3 级解析回退
- [x] 前端 RequirementPage "生成用例"按钮 → 预览弹窗 → 勾选保存
- [x] 复用 `ai_service.call_llm_generate_code()` 不修改 ai_service.py

---

## 第三阶段功能（📋 规划中）

### 7. 场景管理（增强）

- [ ] 场景归属到具体项目（增加 `project_id`）
- [ ] 场景支持软删除和状态管理
- [ ] 场景步骤增强：步骤名称、变量提取规则、请求覆盖配置、断言规则、启用状态

### 8. 真实接口串联

- [ ] 实现运行时 context（变量池）
- [ ] 支持从上一步响应中提取变量（如 token、user_id）
- [ ] 支持在后续请求中使用 `${变量名}` 进行参数替换
- [ ] httpx 顺序执行场景步骤
- [ ] 保存每一步请求、响应、提取变量、断言结果

### 9. 场景执行结果增强

- [ ] 生成可查看的场景执行结果
- [ ] 前端场景执行结果页面增强展示

---

## 后续阶段功能（📋 规划中）

### 10. 测试报告（增强）

- [ ] 报告归属到具体项目（增加 `project_id`）
- [ ] 报告按项目过滤
- [ ] 支持针对特定项目生成报告

### 11. 用户登录

- [ ] 用户注册与登录
- [ ] 基于角色的权限控制
- [ ] 数据按用户隔离

### 12. 前端统一优化

- [ ] 整体 UI 样式统一
- [ ] 响应式布局优化
- [ ] 加载状态和空状态统一

---

## 已有功能（保留不变）

以下功能在 V1.5 Demo 中已实现，各阶段保留不变：

| 功能 | 说明 |
|------|------|
| 接口测试用例 CRUD | 名称、方法、URL、请求头、请求体、期望结果 |
| LLM 生成 pytest 测试代码 | DeepSeek 调用，产出可执行 pytest 代码 |
| 规则生成测试代码 | 纯 Python 确定性生成 |
| pytest 执行 | subprocess 执行，日志采集，响应提取 |
| AI 失败分析 | LLM 根因分析，结构化输出 |
| 场景管理 | 场景 CRUD + 有序步骤 + 场景执行 |
| 测试报告 | 一键执行全部场景 + LLM 汇总报告 |
| 参数管理 | parameter.py 在线编辑 |

---

## 非功能需求

- 后端 API 响应时间 < 5s（LLM 调用除外）
- LLM 调用超时时间 60s
- 前端页面首屏加载 < 3s
- SQLite 单文件数据库，无需独立部署（所有阶段保持不变）
- 支持 Windows / macOS 本地开发运行
