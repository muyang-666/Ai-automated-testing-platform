# V2 对话式 Test Agent 验收清单

> P01～P04 已在各自声明范围通过 Codex 验收。P05 起按 [01_DEVELOPMENT_PLAN.md](01_DEVELOPMENT_PLAN.md)（V2-P05～P10 任务卡）验收（2026-09-04 调整：P07=P07 Artifact Core、P08=P08 Artifact Tools、P09=P09 Chat+MindMap+Diff，不再是旧“Skill / 上下文 / 人工门禁”标题）。旧清单和历史测试记录保留。

## P01 合同

本阶段按 P01 阶段收尾任务提示词（V2-P01_STAGE_COMPLETION_CLAUDE_PROMPT.md，历史文件未随当前目录保留）统一实现与测试；不再仅凭语法检查判定。配对在 P01 验证数据构造关联，真实执行顺序与零副作用在 P03 验证，不把两者混算。

- [x] 普通文本、助手工具调用、工具结果和 UI 事件明确区分。（源码与 90 项阶段测试核实）
- [x] 消息 ID / call_id / schema_version 往返与配对正确。（常规关联及合法早期空调用 ID 形状已验证）
- [x] 内核导入不建库、不初始化真实客户端。（声明范围内的导入/连接保护、独立自检和被捕获尝试判失败已复核；非完整宿主沙箱）
- [x] Pi 当前范围内两层事件可解析，未知事件/非法载荷/关联/原因与版本拒绝。（start/delta 临时块、完成事件及既有异常回归通过）
- [x] 参数纯校验拒绝未知工具/错误参数/截断及未完成响应；不实际调用工具。（固定安全错误、候选构造边界、有效 ID 与 handler 零调用已复核）
- [x] 消息/用量/JSON 边界及合成示例通过阶段针对性测试，记录实际命令与结果。（Codex 实跑 90 passed in 5.41s，见 02 记录 2.10）

最终依据见 [P01 验收记录](reviews/V2-P01_ACCEPTANCE.md)。P01 已结束，现接续 P02；原两次审查及 66/79/90 测试历史保留。

## P02 模型边界

最终依据见 [P02 验收记录](reviews/V2-P02_ACCEPTANCE.md)。真实供应商调用留 P10，不能用 Fake 成绩代替。

- [x] 普通聊天不要求 JSON；显式结构化结果仍严格校验。（旧 complete 回归 55 项通过）
- [x] OpenAI-compatible/Anthropic 的文本、工具分片和结束原因通过 Fake 合同测试。（P02 54 项）
- [x] 空文本但完整 tool_calls 合法；截断/未完成参数绝不执行。（含 `{}`、混合坏参数与 P01 守卫）
- [x] 断流、空结果、拒绝、限流、取消可区分；部分输出不透明重试。（固定 error_code、唯一终态）
- [x] 物理模型尝试使用可共享预算，未知 token 不写 0。（每物理请求 AttemptRecord；P03/P08 后续操作复用同一 AttemptBudget）

## P03 Loop / Tool

最终依据见 [P03 验收记录](reviews/V2-P03_ACCEPTANCE.md)。这里的“真实后续回复”指 Fake 模型链中确有第二次模型调用与最终助手消息，不冒充真实供应商调用。

- [x] 普通回复不执行工具；工具结果传回模型后有真实后续回复。（含 P02 Fake HTTP 集成链）
- [x] 未知工具、错误参数、越权调用被阻止。（默认阻止权限/审批/写工具）
- [x] hook 改参数后重校验；首期工具串行，结果 ID 不串配。（重复 ID 执行前拒绝）
- [x] max_turns / model_calls / tool_calls / deadline 均为硬停止。（Turn 开始前原子预留）
- [x] 工具异常可在预算内反馈，迟到事件不会污染完成消息。（取消后剩余结果也闭合）

## P04 持久化

最终依据见 [P04 验收记录](reviews/V2-P04_ACCEPTANCE.md)。仅临时 SQLite，真实 MySQL 留 P10。

- [x] 无项目/无需求文档可创建私有会话，旧生成入口仍校验项目。（mode 数据库约束）
- [x] 用户消息、Run、幂等键同事务；同键不同请求冲突。（含双连接竞争）
- [x] 序号分配与同会话并发经数据库层验证。（原子行游标，无 Python 全局锁）
- [x] 刷新/重建 Session 能恢复消息和完整工具调用对。（P01 parse_message 复验）
- [x] 外键开启的 SQLite 迁移测试通过；有 conversation 数据时 downgrade 明确拒绝。

## P05 Conversation Runtime 收敛 + Workflow 退役
> 2026-09-04 P05-B/C/D：ConversationRunner 已实现；Worker claim 统一并带 execution_token（fencing）；conversation 执行期由 ownership control loop 做 fenced heartbeat / stale 检测 / cancel 传播 / ownership lost 保护。follow-up 仍未实现（P05-E），对应项不勾选。
- [x] Conversation queued Run 被 Worker 消费（不再跳过、不再永远 queued）；同会话一个活跃 Turn（active_slot 约束不变）。（P05-C Worker E2E：submit→claim→ConversationRunner→succeeded）
- [x] lease / heartbeat / fencing：长模型调用期间 heartbeat 持续刷新（control loop，独立 Session 短事务）；过期/旧 token 执行器写入被拒（fenced heartbeat + 终态前 ownership 复核）；执行中被替换的旧 Worker 不 finalize、不写消息。
- [x] cancel 可终止当前 Turn（DB cancel → Worker control 观察 → cancel_event → AgentLoop abort → Run cancelled，run_cancelled 事件恰好一次）。
- [ ] follow_up 保序且不并行写同一会话；失败/中断后队列暂停。（P05-E，未实现）
- [ ] 中断不自动重放不确定副作用；Worker 未启动时前端可解释。
- [x] 新 Conversation 主路径（Turn → ConversationRunner → Agent Loop）不经过 case_generation / next_step / execute_step。（dispatch 路由测试 + legacy spy 断言）
- [ ] Dependency Audit 完成：旧 Workflow 已隔离到 legacy 或删除；P01～P04 回归通过。

## P06 Conversation API + SSE + 基础工作台
- [ ] 浏览器持续聊天至少三轮，回复来自模型而非前端状态模板；前端“发送”只提交 Turn，不再无条件 createCaseRun。
- [ ] 开始前检查 agent_chat 模型与 Worker 状态，不引用用例场景。
- [ ] SSE Bearer 鉴权、游标重连、增量去重、快照恢复正确。
- [ ] 模型 Key 不进入 URL/前端；Markdown 不执行危险 HTML；刷新恢复与失败后可继续发消息。
- [ ] Tool activity 独立展示（不是伪装的模型答复）；会话 owner 隔离，跨用户不能读消息/事件。
- [ ] 文本→一个纯工具→自然语言解释结果的链路真实走通；模型空内容/截断/超时给出明确诊断，Conversation 不关闭。
- [ ] Fake Provider 经 Worker 完成连续 3 Turn；refresh 后能回答“我刚才最开始给你的数字”类引用问题。
- [ ] 消息、工具结果与摘要跨用户完全隔离（Artifact 的跨用户与并发编辑隔离在 P07 Artifact 域 / P09 UI 域验收，P06 不实现完整 Artifact）。

## Artifact 验收域（P07 Test Artifact Core）
- [ ] Artifact 可独立创建；Tree 可读取；add/update/delete/move node 生效。
- [ ] 每个逻辑写操作产生 Revision（线性连续），并产出结构化 Diff（add/update/delete/move）。
- [ ] Undo（撤销上一 Revision / 恢复到 N）后 UI 与 DB 一致，历史不物理抹除。
- [ ] stale revision 写入返回 409 / revision_conflict，不静默覆盖人工修改。
- [ ] Batch operation 原子（全成功才 commit）；project/user owner 隔离。
- [ ] Artifact Domain 全部可脱离 LLM 用确定性测试验收（构造 20 节点、移动、删除、diff、undo）。

## Conversational Editing 验收域（P08 Artifact Tools + Test Design Skill）
- [ ] 从空 Artifact：先生成测试点，再展开其中几个为详细用例。
- [ ] 不生成测试点也能直接补用例；修改指定节点只影响该节点。
- [ ] “第二个不要”类多轮指代，可结合 Message + 最近 Diff 正确定位并删除。
- [ ] 人工修改 Artifact 后，Agent 下一轮读到的是最新 Revision，而不是缓存旧版。
- [ ] coverage / dedup 是可调用能力而非必经步骤：仅改一条预期时不会强制跑 coverage。
- [ ] Agent 不做无关重写（改 TC003 预期时不会重写整个登录模块；不擅自改分类/重命名）。
- [ ] 8 类对话场景（01 V2-P08）用 Fake Provider 验收通过；写 Tool 契约（expected_revision / audit / Tool Policy）有效。

## UI 验收域（P09 Chat + MindMap + Diff 工作台）
- [ ] Chat 与 MindMap 展示同一 Artifact；AI 添加节点无需刷新即出现。
- [ ] AI 修改后同时产出：Chat 解释 + Changes/Diff 卡 + 脑图更新，三者来自同一 Revision。
- [ ] 人工在脑图/inspector 编辑同样产生 ArtifactOperation → Revision → MindMap 更新。
- [ ] Diff 视图支持 added / updated / deleted / moved。
- [ ] 大范围操作（如删除整分支 43 条）展示 impact preview 并可进入 Approval。
- [ ] 200+ 节点基本交互可用；两个浏览器同时编辑产生 revision conflict 而非静默覆盖。

## P10 Context / Approval / Recovery / E2E
- [ ] 模型输入不整棵塞 Artifact：System + Skill + 摘要 + 最近消息 + 元数据 + 相关节点 + 最近 Diff；不足时 Agent 自调 read/search。
- [ ] 原始消息与工具对保留，compaction 只压缩工作上下文，不删除历史、不拆散 tool_call/tool_result。
- [ ] Approval 按动作风险而非固定 gate：read→allow；add/update 小批量→allow；批量删除/覆盖→approval；写正式项目→approval。审批重新校验参数 hash / revision / 权限 / lease。
- [ ] 恢复与故障注入：Provider 断流 / Worker 崩溃 / Revision 冲突 / Tool timeout / Approval 后恢复 / Cancel / SSE 重连 / Context summary 失败 / Artifact 已写入但 final response 失败；聊天失败不被误报成 Artifact 回滚。
- [ ] 最终 E2E 故事（01 V2-P10：创建 → 列测试点 → 脑图展示 → 展开局部 → “第二个不要” → 补边界 → Diff → Undo → Refresh 恢复）真实跑通。
- [ ] 获得授权后在测试 MySQL 验证迁移/并发/恢复；小额真实模型验证聊天、工具、流式，记录实际结果。
- [ ] 一次版本级受影响 V1/旧 Agent 回归；失败与未运行项如实记录。
- [ ] 三服务启动、预检、停止与回滚可复现；feature flag 可回退。

## 高级测试能力门禁归属
基础测试设计 / 测试点 / 用例协作编辑现在是 V2 纵向闭环的一部分，其验收在上述 Artifact / Conversational Editing / UI / E2E 域中。
API 测试执行、失败根因、造数与缺陷辅助等更高级测试领域的效果与安全门禁移至 [V3 清单](../V3/03_ACCEPTANCE_CHECKLIST.md)。
