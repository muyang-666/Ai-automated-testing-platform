# V2 产品设计：Chat + MindMap + Diff 协作式测试工作台

> 核心体验：测试人员不是让 AI“一键生成完然后结束”，而是和 Agent 围绕同一份测试资产持续工作。

# 1. 产品心智模型

TestMind 不再是：

```text
输入需求
→ 点击生成
→ 等待
→ 获得一份结果
```

而是：

```text
打开测试工作区
→ 和 Agent 对话
→ Artifact 一边讨论一边变化
→ 人工直接修改
→ AI 继续基于最新版工作
```

类比 Coding Agent：

```text
Coding Agent            TestMind

Repository               Test Artifact
Files                    Test Point / Test Case Tree
read_file                read_artifact
edit_file                update_node
create_file              add_node
delete                   delete_node
git diff                 artifact diff
git history              revision history
```

---

# 2. 桌面布局

推荐双主面板：

```text
┌─────────────────────────────────────────────────────────────┐
│ Project / Artifact title             Revision 23   History  │
├────────────────────────┬────────────────────────────────────┤
│ Chat                   │ MindMap                            │
│                        │                                    │
│ User                   │ 登录模块                           │
│ Assistant              │ ├─ 正常登录                        │
│ Tool activity          │ ├─ 密码错误                        │
│ Diff card              │ └─ 账号锁定                        │
│                        │    ├─ 第4次失败                     │
│                        │    ├─ 第5次失败                     │
│                        │    └─ 30分钟解锁                    │
│                        │                                    │
│ [message input......]  │ [node inspector]                   │
└────────────────────────┴────────────────────────────────────┘
```

移动端可以 Tab 切换：

```text
Chat | MindMap | Changes
```

---

# 3. 对话中的 Artifact Context

输入框上方显示当前工作对象：

```text
Working on:
登录模块测试设计
Revision 23
```

用户可以切换：

```text
Artifact A
Artifact B
```

但正在运行的 Turn 不允许静默切换 Artifact。

切换后新 Turn 使用新 Context。

---

# 4. AI 修改反馈

AI 不应该只说：

```text
已完成。
```

应该同时产生：

### Chat

```text
我补充了账号锁定的 3 个时间边界场景。
```

### Changes

```text
Revision 24

+ TC021 29分59秒仍锁定
+ TC022 30分钟整允许重新登录
+ TC023 30分01秒保持正常登录
```

### MindMap

对应节点出现。

三个视图来源都是同一个 Revision。

---

# 5. 人工编辑

用户可以：

- 改标题；
- 改前置条件；
- 改步骤；
- 改预期；
- 拖动节点；
- 新增节点；
- 删除节点。

人工编辑也必须生成 `ArtifactOperation`。

例如：

```text
User UI edit
→ PATCH/operation
→ Revision 25
→ Event
→ MindMap update
```

下一轮 Agent 看到 Revision 25。

---

# 6. Node Inspector

点击 TestCase 节点：

```text
TC021
29分59秒仍锁定

Priority: P1
Tags: 边界 / 状态

Preconditions
- 已连续失败 5 次

Steps
1. 等待 29分59秒
2. 输入正确密码

Expected
- 登录失败
- 提示账号仍处于锁定状态

Sources
REQ-12 / clause-7
```

脑图负责结构，Inspector 负责详细字段。

---

# 7. Changes / Diff

Diff 不是日志字符串，而是结构化 UI。

支持：

```text
Added
Updated
Deleted
Moved
```

Update 示例：

```text
TC012 / Expected Result

- 锁定后无法登录
+ 锁定期间即使密码正确也无法登录
```

Move 示例：

```text
TC023
Password Error
→ Lock Time Boundary
```

---

# 8. Undo / History

History：

```text
Revision 25  You     修改 TC021 预期
Revision 24  Agent   添加 3 个边界场景
Revision 23  Agent   展开账号锁定
Revision 22  You     删除账号不存在
```

用户点击：

```text
Undo Revision 25
```

产生新的 Revert Revision。

不要直接抹去历史。

---

# 9. Approval UI

不再展示：

```text
Workflow coverage_gate
```

而展示真实动作：

```text
Agent wants to delete 43 test cases

Target:
支付 / 退款旧流程

Impact:
1 group
8 test points
34 test cases

[Review changes] [Approve] [Reject]
```

用户理解的是动作，而不是 Runtime phase。

---

# 10. Agent Tool Activity

可以显示：

```text
✓ 读取登录需求
✓ 查看账号锁定节点
✓ 新增 3 个测试用例
```

不要显示：

```text
模型正在想……
```

也不要泄漏隐藏 reasoning。

---

# 11. Streaming 与 Artifact 修改

聊天文字可以 streaming。

Artifact 写操作则推荐按完整 ToolCall 成功后一次提交 Revision。

不要：

```text
LLM token 一边流
→ 数据库节点一边半成品写
```

正确：

```text
tool arguments complete
→ validate
→ transaction
→ revision committed
→ UI receive artifact_revision_created
```

---

# 12. “AI 写用例”的典型用户故事

## Story A

用户：

```text
根据这个登录需求先列一下测试点
```

结果：

- Chat 解释；
- MindMap 出现 TestPoint；
- 不生成详细用例。

---

## Story B

用户：

```text
锁定这里感觉少了边界，补一下
```

结果：

- Agent 读取锁定节点；
- 根据需求补局部；
- Diff 只影响该分支。

---

## Story C

用户：

```text
第二条不要，第三条预期改成“30分钟后立即解锁”
```

结果：

- Agent 利用上一轮 Diff 解析指代；
- 删除 TC022；
- 修改 TC023；
- 一个新的 Revision 展示两个 changes。

---

## Story D

用户手工编辑一条用例后说：

```text
按我刚改的这种写法，把同组剩下几条统一一下。
```

Agent 必须读取最新 Revision，再修改。

这是“AI + 人工共同维护 Artifact”的关键体验。

---

# 13. 首期不做

P09 首期可以不做：

- 无限画布高级排版；
- 多人实时 CRDT；
- Git 式分支；
- 评论系统；
- 多 Artifact 同屏；
- 自动合并复杂冲突；
- 全功能 XMind 兼容。

先保证：

```text
Chat ↔ Artifact ↔ MindMap ↔ Diff ↔ Revision
```

闭环成立。

---

# 14. 产品验收指标

功能验收：

- 100% AI 写操作产生 Revision；
- 100% 人工写操作产生 Revision；
- stale write 不静默覆盖；
- refresh 后 Chat / Tree / Revision 一致；
- AI 可处理局部修改；
- 不要求每次从头生成；
- Undo 可恢复。

体验验收：

用户应该感觉：

> “我不是让 AI 帮我生成一份用例，我是在和 AI 一起维护这份用例。”
