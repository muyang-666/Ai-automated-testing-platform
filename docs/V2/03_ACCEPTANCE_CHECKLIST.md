# TestMind V2 验收清单

> 使用规则：只有存在真实测试、命令输出、接口结果或人工验证证据时才能勾选。
>
> 未达到当前版本全部硬门禁时，不进入下一版本。

## 1. 通用硬门禁

- [ ] 所有 Agent 输入和输出通过 Pydantic/JSON Schema 校验。
- [ ] 所有 Agent 工具均在白名单注册，没有任意 SQL、Shell、文件或 URL 工具。
- [ ] 每次工具调用重新校验 user_id 和 project_id 权限。
- [ ] 跨项目未授权读取和写入测试全部被拒绝。
- [ ] Authorization、Cookie、Token、password、secret、API Key 不进入模型出站内容和持久化轨迹。
- [ ] 需求、接口文档、日志和响应不能修改系统策略或工具权限。
- [ ] 未经人工审批自动保存用例数为 0。
- [ ] 未经人工审批自动重跑或主动探测数为 0。
- [ ] 最大步骤、模型调用、工具调用、token 和总超时限制生效。
- [ ] 不保存模型隐藏思维链。
- [ ] 所有数据库 migration upgrade/downgrade 通过。
- [ ] legacy 链路可通过 feature flag 或旧接口回滚。
- [ ] 文档状态与真实实现一致。

## 2. V1 回归门禁

- [ ] 用户登录和项目权限正常。
- [ ] 项目、模块、需求和接口文档 CRUD 正常。
- [ ] 接口用例和功能用例 CRUD 正常。
- [ ] V1 功能用例生成接口正常。
- [ ] V1 接口用例生成接口正常。
- [ ] 规则生成 pytest 正常。
- [ ] pytest 执行、日志和响应采集正常。
- [ ] 场景串联执行、变量提取和断言正常。
- [ ] V1 失败分析接口仍可用或有明确兼容入口。
- [ ] 报告生成和查询正常。
- [ ] 前端 `npm run build` 通过。

## 3. V2.1 用例生成 Agent

### 3.1 Baseline 与基础设施

- [x] requirement 和 api_document 的 V1 baseline 测试不调用真实 LLM。（2026-09-01 V2.1-T01：33 个测试通过，Fake LLM + 内存 SQLite + mock 环境变量，证据见 02_DEVELOPMENT_RECORD.md）
- [x] Alembic 可初始化现有数据库且不丢失 V1 数据。（2026-09-01 V2.1-T02：存量库 stamp 0001 → upgrade head 流程在临时 SQLite 验证，V1 21 张表在 upgrade/downgrade 全程保留；真实 MySQL 验证登记为后续测试环境验证项）
- [x] agent_runs 和 agent_steps 迁移可回滚。（2026-09-01 V2.1-T02：0002 downgrade 删除全部 7 张 agent 表且 V1 表保留、再次 upgrade 成功，SQLite 验证，证据见 02_DEVELOPMENT_RECORD.md）
- [x] LLM Gateway 区分配置、超时、Provider 和输出校验错误。（2026-09-02 V2.1-T03：LLMConfigurationError/LLMTimeoutError/LLMProviderError/LLMRateLimitError/LLMOutputValidationError/LLMUnsupportedFeatureError，52 条测试覆盖，证据见 02_DEVELOPMENT_RECORD.md）
- [x] 429/5xx 有界重试，其他错误不盲目重试或错误回退。（2026-09-02 V2.1-T03：Gateway 内 max_retries=2 指数退避、sleeper 可注入；400/401/403 与校验错误不重试；`call_llm_by_scene` 只在配置不可用时回退 .env，Provider 调用失败不回退）
- [x] Agent Worker 不重复抢占同一任务。（2026-09-02 V2.1-T04B：条件 UPDATE `WHERE id AND status='queued'` + rowcount 判定，双 Session 竞争测试验证第二个 Worker rowcount=0；cancelled/waiting_approval/终态不可抢占）
- [x] queued/running/waiting_approval/succeeded/failed/cancelled/interrupted 状态可测试。（2026-09-02 V2.1-T04A：transitions.py 集中转换表 + AgentRunner 推进，63 条新增测试覆盖合法/非法/终态/预算/取消）
- [x] AgentSession、Message、Event、Run、Step、Artifact 和 Approval 关联正确。（2026-09-02 V2.1-T04A：四个平台 Service + Runtime 测试验证外键关联、sequence_no/version 递增）
- [x] Skill Registry 只加载已注册和已审核的 Skill。（2026-09-02 V2.1-T04A：内存注册表，code 唯一、重复/未知报错、不动态 import、不扫描 SKILL.md；生产业务 Skill 尚未实现）
- [x] Claude Adapter 和 OpenAI-compatible Adapter 具有统一调用合同。（2026-09-02 V2.1-T03：统一 LLMProviderAdapter 协议 + LLMRequest/LLMResult 合同；Anthropic SDK 客户端 max_retries=0 由 Gateway 统一重试）

### 3.2 Agent 工具与 Workflow

- [x] 用户可通过显式 skill_code 启动 case_generation Skill。（2026-09-02 V2.1-T06：create_run(workflow_code="case_generation") + Runner/Worker 执行；对话路由留 T08）
- [x] 从需求/接口文档点击“交给 Agent”可自动挂载来源上下文。（2026-09-03 T08：两页入口传递来源/项目，同一事件合同在隔离联调页验证；正式登录整页场景待真实测试环境验收）
- [x] 范围确认和覆盖计划确认均形成可恢复 GATE。（2026-09-02 V2.1-T06：两个确认 GATE + 保存审批 GATE，恢复时按 (run_id, action_code) 查现有 Approval 不重复创建）
- [x] 支持 requirement 和 api_document 两种来源。（2026-09-02 V2.1-T06：双 happy path 集成测试通过）
- [x] Agent 能读取项目、模块和已有用例上下文。（2026-09-02 V2.1-T05：load_source_context / load_project_module_context / list_existing_cases / list_related_api_documents，均带项目权限校验）
- [x] 原子条款具有稳定 clause_id。（2026-09-02 V2.1-T06：模型建议后经程序去重与格式校验，非法格式替换为 REQ-NNN）
- [x] 候选用例能追踪 covered_clause_ids。（2026-09-02 V2.1-T05：compute_coverage_matrix 按 covered_clause_ids 确定性聚合，未知条款引用进 unknown_refs）
- [x] 未知接口、字段和规则进入 assumptions。（2026-09-02 V2.1-T06：analyze_and_plan 输出 assumptions 并写入 State/coverage_matrix Artifact）
- [x] Schema、业务规则、去重和覆盖矩阵由确定性代码执行。（2026-09-02 V2.1-T05：case_validators 纯函数 + 三个校验工具；T05.1 修复指纹为场景级 SHA-256 摘要，同接口不同场景不再误删，248 测试覆盖）
- [x] dry-run 不写数据库、不写文件、不发送请求。（2026-09-02 V2.1-T05：dry_run_api_case_codegen 复用 ai_service 纯内存函数，测试断言 APICase 行数不变且 file_writer 未被调用）
- [x] 修正只针对缺口和非法候选。（2026-09-02 V2.1-T06：repair prompt 只输入校验错误/重复摘要/缺失覆盖/问题候选子集，禁止全量重生成）
- [x] 修正轮次不超过 2，模型调用不超过 4。（2026-09-02 V2.1-T06：集成测试验证 repair_round==2 与 llm_calls==4 上限）
- [x] 达到停止条件后不继续生成。（2026-09-02 V2.1-T06：无缺口即结束、上限后保留有效候选并如实 warnings、零候选 failed）

### 3.3 API 与前端

- [x] 创建任务立即返回 202 和 run_id。（2026-09-02 V2.1-T07：POST /agent/runs/case-generation 返回 202+queued，不直接执行）
- [x] 创建会话前校验项目存在/未删除/active、项目可操作权限、来源存在且归属一致；非法项目/孤立来源返回稳定 4xx 而非 500。（2026-09-03 V2.1-T08.1：11 条 API + 6 条 Service 针对性用例；隔离库开启并断言 SQLite 外键；证据见 02 开发记录第 19 节）
- [x] Agent 相关回归库在 SQLite 外键开启下无连带破坏。（2026-09-03 V2.1-T08.1：250 条 agent 相关 + 149 条 services/providers/skills 用例通过）
- [ ] 正式环境历史孤立来源（requirement_docs 引用不存在项目）经数据处置后可正常生成。（V2.1-T08.1 仅让错误可理解并阻止新增脏会话，项目数据恢复/需求归属修复待用户决策后人工执行）
- [ ] 状态、步骤、取消、refine 和保存接口权限正确。（状态/步骤/取消/保存已实现并测试；refine 端点留 T08，故不勾选）
- [x] 保存只接受 candidate_id，后端重新加载和校验候选。（2026-09-02 V2.1-T07：数据全部取自 test_case_set Artifact 与 Run/State，不信任前端 payload/project_id）
- [x] 重复保存幂等。（2026-09-02 V2.1-T07：相同 candidate_ids 返回相同 saved_case_ids（resolution_json 持久化），不同 ids 返回 409）
- [x] 非 waiting_approval 任务不能保存。（2026-09-02 V2.1-T07：agent_save_not_awaiting → 409；幂等重复保存除外）
- [x] 页面展示 Agent 进度、候选、覆盖、假设和警告。（2026-09-03 T08：实际 Artifact 合同适配；假设/警告按 payload 展示）
- [x] Agent 工作台同时提供对话区、GATE 卡片和 Artifact 工作区。（2026-09-03 T08：悬浮可拖动/缩放，浏览器双来源主闭环验证）
- [x] 会话关闭后可恢复消息、事件、当前 Skill Run 和 Artifact。（2026-09-03 T08：浏览器刷新恢复最近会话和最近 Run；并非后端 closed 会话重新激活）
- [ ] 用户可取消任务、局部修正并勾选保存。（T08 已验证取消/勾选保存；自由局部 refine 无 API 合同，暂不勾选整体）
- [x] legacy/agent 入口可切换。（T08 保留两页原有生成按钮并增加“交给 Agent”，未替换 legacy 默认行为；全量 V1 回归仍留发布验收）

### 3.4 评测与发布

- [ ] 固定评测集和版本信息已记录。
- [ ] legacy/agent 使用同一批输入对比。
- [ ] 输出条款覆盖率、重复率、幻觉率、专家接受率、延迟和 token 的真实结果。
- [ ] 通用硬门禁全部通过。
- [ ] V1 回归全部通过。
- [ ] 评测未通过时保持 legacy 默认。

## 4. V2.2 根因分析 Agent

### 4.1 冻结证据

- [ ] TestRun 保存用例定义快照和 hash。
- [ ] TestRun 保存实际执行代码快照和 code hash。
- [ ] 保存实际请求摘要、exit code、timeout 和 duration。
- [ ] 保存 Python、pytest、runner/parser version。
- [ ] 分析旧运行不读取变化后的当前代码冒充运行代码。
- [ ] pytest subprocess 设置可验证的 timeout。

### 4.2 确定性工具

- [ ] parse_pytest_failure 可提取异常、位置、expected/actual 和 traceback。
- [ ] audit_generated_code 只做 AST/compile/规则检查，不执行代码。
- [ ] compare_case_history 可以识别稳定回归和偶发波动证据。
- [ ] load_scene_trace 可以读取失败步骤及上游变量链。
- [ ] lookup_api_contract 只能查询用户有权访问的项目数据。
- [ ] 所有出站证据先脱敏。

### 4.3 Workflow 与输出

- [ ] 支持 confirmed/likely/inconclusive。
- [ ] primary_cause、hypotheses、evidence、recommendations 和 missing_evidence 结构稳定。
- [ ] confidence 与 risk_level 分离。
- [ ] 每个事实性结论绑定可解析 evidence_id。
- [ ] 无证据高置信输出被 Validator 拒绝。
- [ ] 模型调用不超过 2、工具调用不超过 6、额外取证不超过 1 轮。
- [ ] 默认不存在自动重跑和任意网络探测。

### 4.4 API、前端和评测

- [ ] 查看已有分析与重新分析分离。
- [ ] 同一 context hash 不重复创建活跃任务。
- [ ] 单用例页面展示结构化根因和证据。
- [ ] 场景失败页面展示上游变量和断言证据。
- [ ] 前端不再用正则解析 Agent 自由文本。
- [ ] 固定评测集覆盖六大主分类和典型异常。
- [ ] 输出分类、证据、inconclusive、稳定性、延迟和 token 的真实结果。
- [ ] 通用硬门禁和 V1 回归全部通过。

## 5. V2.3 测试 Skill 扩展与细节优化

- [ ] Prompt Injection 和递归脱敏测试进入自动化门禁。
- [ ] 结构化日志可按 run_id、step_id、project_id、user_id 检索。
- [ ] token、延迟、错误和重试可统计。
- [ ] heartbeat 和中断恢复经过故障测试。
- [ ] 覆盖矩阵和根因证据页面完成人工可用性验收。
- [ ] 固定离线评测集有版本管理。
- [ ] 轨迹评测只检查可观察工具和顺序约束。
- [ ] AgentStep 大字段、保留周期和删除关联有明确策略。
- [ ] 数据库索引、分页和慢查询经过验证。
- [ ] 测试数据准备 Skill 优先查询/复用，写操作限定测试环境并强制 Approval。
- [ ] 造数 Tool 不接受模型生成的任意 SQL 直接执行。
- [ ] 缺陷描述 Skill 生成结构化 defect_draft Artifact 并绑定证据。
- [ ] 缺陷草稿只有用户确认后才能复制或提交外部系统。
- [ ] V1、V2.1、V2.2 全量回归通过。

## 6. V2.4

- [ ] 用户与 Codex 已根据真实数据确定 V2.4 目标。
- [ ] 在目标确定前，没有提前新增 V2.4 代码、表、接口或依赖。
