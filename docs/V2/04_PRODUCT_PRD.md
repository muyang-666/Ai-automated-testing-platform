# V2 产品 PRD：对话式 Test Agent 与可持续测试资产工作台

> 本文件只回答“产品应该是什么样”。数据模型、工具合同与实现协议见 [05_TECHNICAL_DESIGN.md](05_TECHNICAL_DESIGN.md)；开发路线见 [01_DEVELOPMENT_PLAN.md](01_DEVELOPMENT_PLAN.md)。

## 1. 产品定位

**TestMind V2 是一个面向测试人员的对话式 Test Agent 工作台**：用户可以像使用 Coding Agent 修改代码一样，通过持续对话让 AI 读取、创建、修改、重构和检查测试资产，并以脑图等结构化视图实时协作。

测试人员不是让 AI“一键生成完然后结束”，而是与 Agent 围绕同一份测试资产持续工作。测试用例不是一次 Workflow 的最终输出，而是类似代码仓库的长期 Artifact。

设计口号：

> **Test Cases as Code；Agent as Collaborator。**

“as Code”不要求用例一定是 Python，而是强调测试资产具备：结构化、可增量编辑、可 Diff、可版本化、可审查、可恢复、可持续演进。

产品体验对比：

| Coding Agent | TestMind |
|---|---|
| Repository | Test Artifact |
| Files | Test Point / Test Case Tree |
| read_file | read_artifact |
| edit_file | update_node |
| create_file | add_node |
| delete | delete_node |
| git diff | artifact diff |
| git history / undo | revision history / undo |

## 2. 核心体验：持续 Conversation

登录后即可持续对话，创建或打开一个测试 Artifact（无需先绑定项目或接口文档）。用户的每一句只是新的输入，由 Agent 决定下一步：直接回复、读取需求/Artifact、加载 Skill、或调用 Artifact 工具修改测试资产。

测试设计不存在强制路径。用户可以：

```text
先分析需求 → 先列测试点 → 删除部分测试点 → 展开其中三个测试点
→ 手工修改一条用例 → 让 AI 补边界场景 → 查重 → 暂时不保存 → 第二天继续
```

也可以直接“读取已有用例 → 找缺失场景 → 修改 TC023”，或“不要生成测试点，直接给现有脑图补 3 个异常场景”。

## 3. Test Artifact

Test Artifact 是长期存在、用户与 Agent 共同维护的测试资产（类似代码仓库/文档/设计文件），不是“模型回答附件”。它需要具备：稳定 ID、Revision、结构化树（测试点/用例）、Diff、History、Undo、来源引用、项目归属。

Agent 修改 Artifact 时，聊天负责解释，Artifact 负责保存修改。两种内容不互相冒充。

## 4. 工作台布局：Chat + MindMap + Diff

推荐桌面双主面板：

```text
┌────────────────────────────────────────────────────────────┐
│ Project / Artifact title             Revision 23  History   │
├────────────────────────┬───────────────────────────────────┤
│ Chat                   │ MindMap                           │
│                        │                                   │
│ User                   │ 登录模块                          │
│ Assistant              │ ├─ 正常登录                       │
│ Tool activity          │ ├─ 密码错误                       │
│ Diff card              │ └─ 账号锁定                       │
│                        │    ├─ 第4次失败                    │
│                        │    ├─ 第5次失败                    │
│                        │    └─ 30分钟解锁                   │
│ [message input......]  │ [node inspector]                  │
└────────────────────────┴───────────────────────────────────┘
```

移动端可 Tab 切换：`Chat | MindMap | Changes`。

- **输入框上方显示当前工作对象**：`Working on: 登录模块测试设计 · Revision 23`；可切换 Artifact，但正在运行的 Turn 不允许静默切换，切换后新 Turn 使用新 Context。
- **MindMap 负责结构，Node Inspector 负责详细字段**：点击 TestCase 显示标题、Priority、Tags、Preconditions、Steps、Expected、Sources（如 REQ-12 / clause-7）。
- 会话列表可恢复历史；运行中切换展示不能让请求/结果串会话。

## 5. 修改反馈：Chat + Changes + MindMap 三视图同源

AI 不应只说“已完成”。一次修改应同时产出：

- **Chat**：`我补充了账号锁定的 3 个时间边界场景。`
- **Changes/Diff**：结构化变更卡（见 §7）。
- **MindMap**：对应节点出现。

三个视图的来源都是同一个 Revision（或同一批操作）。

## 6. 人工与 AI 协作

用户可以改标题、前置条件、步骤、预期，拖拽节点，新增/删除节点。**人工编辑同样产生 ArtifactOperation → Revision**，下一轮 Agent 读取到的就是人工修改后的最新版。

典型体验（Story D）：用户手工改一条用例后说“按我刚改的这种写法，把同组剩下几条统一一下” —— Agent 必须读取最新 Revision 后再修改。这是“AI + 人工共同维护 Artifact”的关键体验。

## 7. Changes / Diff

Diff 不是日志字符串，而是结构化 UI，支持 added / updated / deleted / moved：

```text
Update 示例：
TC012 / Expected Result
- 锁定后无法登录
+ 锁定期间即使密码正确也无法登录

Move 示例：
TC023
Password Error → Lock Time Boundary
```

## 8. Revision History / Undo

History 展示可追溯的记录：

```text
Revision 25  You     修改 TC021 预期
Revision 24  Agent   添加 3 个边界场景
Revision 23  Agent   展开账号锁定
Revision 22  You     删除账号不存在
```

用户点击 Undo（撤销上一修改 / 恢复到某个 Revision）时，系统生成反向 Revision，**不直接抹去历史**。

## 9. Approval UX

产品上不展示“Workflow coverage_gate”之类的运行时阶段，而是展示真实动作及其影响：

```text
Agent wants to delete 43 test cases

Target:  支付 / 退款旧流程
Impact:  1 group / 8 test points / 34 test cases

[Review changes] [Approve] [Reject]
```

用户理解的是动作，而不是 Runtime phase。审批请求绑定具体动作、参数与版本，过期或参数变化后必须重新确认。

## 10. 输入输出与过程展示

- 输入支持普通文本、可选显式 Skill、后续消息排队。多模态、上传可执行文件、任意网址工具不在 V2。
- 回复为自然语言/Markdown，可逐步流式展示。
- 系统进度、Tool 轨迹、Diff/Changes 与错误是独立 UI，不伪装成模型思考或回答；**不展示隐藏思维链**。
- Tool activity 展示行为：`✓ 读取登录需求 / ✓ 查看账号锁定节点 / ✓ 新增 3 个测试用例`；不展示“模型正在想……”。
- 聊天文字可以流式；Artifact 修改按完整 ToolCall 成功后一次性提交 Revision，不出现“token 边流边写半成品节点”。
- 运行时显示停止与排队行为；失败/取消后输入框恢复可用。模型未配置、Worker 未就绪要在开始前解释。
- JSON 只是部分内部合同格式，不是所有用户可见回复的格式要求。

## 11. Skill 的产品边界

Skill 是可发现的任务能力说明与行为规则（如 test-design：怎么提炼测试点、补边界、做增量编辑），它不是固定 phase 状态机，也不是获得额外权限的钥匙。
用户说“生成用例”时，Agent 按对话上下文与 Artifact 状态工作，而不是每次都启动同一个固定生成流程；尚未接入的高级能力（API 测试执行、RCA、造数、外部提交等）应明确告知未启用，不假装成功。

## 12. 身份与确认

聊天不要求项目，但仍要求登录与 owner 隔离。读项目需求必须先绑定授权项目并验证权限；普通聊天不能获得跨项目搜索权。
有副作用的动作按风险决定是否需要可见确认：读与小幅增删改直接执行；批量删除、覆盖整个 Artifact、写正式项目等进入 Approval（见 §9）。聊天中的“解释一下”不是执行许可，Skill 文本不是审批凭证。

## 13. 典型用户故事

**Story A —— 先列测试点**
用户：`根据这个登录需求先列一下测试点。`
结果：Chat 解释 + MindMap 出现 TestPoint，不生成详细用例。

**Story B —— 局部补边界**
用户：`锁定这里感觉少了边界，补一下。`
结果：Agent 读取锁定分支与相关需求，只补局部；Diff 只影响该分支。

**Story C —— 多轮指代**
用户：`第二条不要，第三条预期改成“30分钟后立即解锁”。`
结果：Agent 利用上一轮 Diff 解析指代（第二个 = 上一轮新增的第二个节点），删除 TC022、修改 TC023，一个新 Revision 展示两个 changes。

**Story D —— 跟随人工风格**
用户手工编辑一条用例后：`按我刚改的这种写法，把同组剩下几条统一一下。`
结果：Agent 读取最新 Revision 后修改同组其余用例。

**Story E —— 查重与补缺口分离**
用户：`看看有没有重复。` → Agent 查重并解释，不自动改。
用户随后：`把缺口补上。` → 先展示缺口清单，同意后再补。

**Story F —— 覆盖与撤销**
用户：`检查覆盖，再 Undo 一次。` → Agent 调 coverage/read 工具报告缺口；Undo 后 UI 与数据库一致。

**Story G —— 刷新与续作**
用户刷新页面，第二天回来：同一 Conversation、Artifact、Revision 历史完整恢复，可继续对话编辑。

## 14. 首期不做

- 无限画布高级排版；多人实时 CRDT；Git 式分支；评论系统；多 Artifact 同屏；自动合并复杂冲突；全功能 XMind 兼容。
- 先保证 `Chat ↔ Artifact ↔ MindMap ↔ Diff ↔ Revision` 闭环成立。

## 15. V2 非目标（产品边界）

- API 测试执行、失败根因分析、测试造数、缺陷辅助、执行/CI 集成属于 [V3](../V3/README.md) 更高级测试能力；它们复用同一 Conversation + Agent Loop + Tools + Artifact 模型，而不是各自做成固定流程任务。
- 任意 Shell/SQL/URL/宿主文件工具、自动下载扩展、npm 插件体系、TUI 不在 V2。
- V2 不是“通用聊天外壳”也不是“一键生成用例工具”：离开 Artifact 的纯聊天只用于开始一段工作，最终价值围绕可持续测试资产。

## 16. 产品验收指标

功能验收：
- 100% AI 写操作产生 Revision；100% 人工写操作产生 Revision；
- stale write 不静默覆盖；refresh 后 Chat / Tree / Revision 一致；
- AI 可处理局部修改；不要求每次从头生成；Undo 可恢复。

体验验收：用户应该感觉

> “我不是让 AI 帮我生成一份用例，我是在和 AI 一起维护这份用例。”
