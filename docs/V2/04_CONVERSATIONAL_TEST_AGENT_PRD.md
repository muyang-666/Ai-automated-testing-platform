# V2 对话式 Test Agent PRD

> 产品目标：成为一个可持续交流、并围绕测试 Artifact 持续协作编辑的 Test Agent。
> 用户像使用 Coding Agent 修改代码一样，用自然语言让 Agent 读取、创建、修改、删除、重构和检查测试资产，也可以直接在脑图中人工编辑；两者走同一 Artifact 与 Revision。
> 测试设计不是一次性固定 Workflow：不存在“先生成测试点→再生成用例→强制查重→强制覆盖→保存”的必经路径。路线与对象见 [11_V2_DIRECTION_ADR.md](11_V2_DIRECTION_ADR.md)、[12_POST_P04_DEVELOPMENT_PLAN.md](12_POST_P04_DEVELOPMENT_PLAN.md)；产品体验细化见 [15_CHAT_MINDMAP_DIFF_PRODUCT_DESIGN.md](15_CHAT_MINDMAP_DIFF_PRODUCT_DESIGN.md)。

## 1. 用户体验

- 登录后即可与 Agent 持续对话，创建或打开一个测试 Artifact（如“登录模块测试设计”），无需先绑定项目或接口文档。
- 用户的每一句都只是新的输入，由模型决定下一步：直接回复、读取需求/Artifact、加载 Skill、或调用 Artifact 工具修改测试资产。
- “根据这段登录需求先列测试点”——Agent 读取需求并在 Artifact 中新增测试点，脑图实时出现。
- “锁定这里补一下边界”——Agent 只读取并修改“账号锁定”相关分支，不动其它分支。
- “第二个不要”——Agent 结合上一轮 Diff 判断指代，删除对应节点。
- 用户直接在脑图手工改一条用例后说“按我刚改的写法，把同组剩下的统一一下”——Agent 读取最新 Revision 后再继续修改。
- 普通回复不是 JSON 产物；一次模型失败后会话仍可用，可继续发消息。

## 2. 输入和输出

输入支持普通文本、可选显式 Skill、后续消息排队。多模态、上传可执行文件、任意网址工具不在 V2。
回复为自然语言/Markdown，逐步流式展示。系统进度、工具轨迹、Diff/Changes 与错误是独立 UI，不伪装成模型思考或回答；不展示隐藏思维链。
Artifact 写操作不逐 token 半成品落库：Tool 参数完整 → 校验 → 单事务 → Revision 提交 → UI 收到事件。

## 3. 工作台：Chat + MindMap + Diff

- Chat：对话与 Agent 的工具活动；AI 修改后给出解释，并附带 Changes/Diff。
- MindMap：Artifact 的结构化实时视图；用户可新增/改标题/改字段/拖拽/删除节点。
- Changes/Diff：结构化展示 added / updated / deleted / moved；Update 显示字段级 before/after。
- History / Undo：Revision 历史（谁在什么时候改了什么），点击 Undo 生成反向 Revision，不抹除历史。
- Node Inspector：选中 TestCase 显示前置/步骤/预期/优先级/标签/来源。
- 工作对象切换：可切换 Artifact，但正在运行的 Turn 不允许静默切换。

## 4. Skill 与 Artifact Tools 边界

Skill 是可发现的任务能力说明与行为规则（例如 test-design），用于指导 Agent 怎么分析测试点、补边界、增量编辑；它不再是固定 phase 状态机，也不是额外权限的钥匙。
Agent 通过受控 Tool 读写 Artifact（read / add / update / delete / move / validate / coverage），身份与权限由程序注入，所有写操作要求 expected_revision 并产生 Revision/Diff。
用户说“删除整个支付分支 43 条”“覆盖整个 Artifact”“写入正式项目”时，进入按动作风险的 Approval，而不是某个固定 Workflow gate。

## 5. 身份与确认

聊天仍要求登录与 owner 隔离；身份从登录态取得，不信任模型传入的 user/project/owner。
读项目需求必须先绑定授权项目并验证权限；普通聊天不能获得跨项目搜索权。
有副作用的动作按风险决定是否可见确认；聊天中的“解释一下”不是执行许可，Skill 文本不是审批凭证。

## 6. 产品验收故事

1. “先列登录模块测试点”：Artifact 增加测试点，脑图即时出现，聊天给解释。
2. “锁定这块补边界”：Diff 只影响该分支。
3. “第二条不要，第三条预期改成 …”：用上一轮 Diff 解析指代，正确删除/修改。
4. 用户手工编辑一条用例后要求“按这种写法统一同组剩余几条”：Agent 基于最新 Revision 工作。
5. “看看有没有重复”：Agent 调查重但不强制改；随后仅按要求补缺口。
6. “不要生成测试点，直接补 3 个异常场景”：不强制先生成测试点。
7. 删除大分支前 UI 展示 impact preview 并请求 Approval；未批准零副作用。
8. 运行中最小化/刷新 → 同一会话与 Artifact/Revision 恢复，不重复执行。
9. 撤销上一修改后 UI 与 DB 一致；第二天继续同一 Conversation，仍能看到 Revision 历史并继续编辑。

## 7. 不做（V2 边界内）

API 测试执行、失败根因分析、测试造数与缺陷辅助属于 [V3](../V3/README.md) 更高级测试能力；它们未来复用同一 Conversation + Agent Loop + Tools + Artifact 模型，而不是各自新做一个固定 Workflow Runtime。
