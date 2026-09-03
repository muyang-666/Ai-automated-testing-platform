# Pi 源码阅读与 Python 实现对照

> 本文来自实际源码阅读，不只依据 README。检索日期：2026-09-03。
> 上游目录：D:\pi；origin：https://github.com/earendil-works/pi.git。
> 参考 commit：f41f80466e30f21cdcd4d52aba4a2c2cb6ee3cc6，标题：fix(coding-agent): update interactive mode test fixture。
> 状态：已阅读/已规划；未移植、未安装 npm 依赖、未运行上游测试。

## 1. 固定版本的方法

先通过 GitHub 官方内容 API 阅读 bea67d90d1a74dde8852c63cac72d476013d3879 的 8 个关键文件；随后完整克隆仓库，HEAD 为以上参考 commit。已用 git diff 检查两个提交间 packages/agent、ai/src/types.ts、coding-agent/core/agent-session.ts 和 session-manager.ts 无差异。下方统一链接到克隆的参考提交。

只读查看命令（不切分支、不执行源码）：

~~~powershell
git -C D:\pi rev-parse HEAD
git -C D:\pi show f41f80466e30f21cdcd4d52aba4a2c2cb6ee3cc6:packages/agent/src/agent-loop.ts
git -C D:\pi show f41f80466e30f21cdcd4d52aba4a2c2cb6ee3cc6:packages/agent/test/agent-loop.test.ts
~~~

实施者必须对照固定提交。若需要升级基线，单独记录差异，不用 main 的浮动行号证明旧版本行为。

## 2. 源码层次与采纳范围

| 上游源码（固定链接） | 已核查的关键符号/行为 | Python 目标 | 任务 |
|---|---|---|---|
| [ai/src/types.ts](https://github.com/earendil-works/pi/blob/f41f80466e30f21cdcd4d52aba4a2c2cb6ee3cc6/packages/ai/src/types.ts) | TextContent、ToolCall、AssistantMessage、ToolResultMessage、Usage、StopReason；文本和工具块分开 | 复用并扩展 LLMMessage/Result；协议边界归一化 | P01/P02 |
| [agent/src/types.ts](https://github.com/earendil-works/pi/blob/f41f80466e30f21cdcd4d52aba4a2c2cb6ee3cc6/packages/agent/src/types.ts) | AgentContext、AgentTool、AgentEvent、before/afterToolCall、prepareNextTurn、shouldStopAfterTurn | conversation/contracts.py、events.py、policy.py | P01/P03 |
| [agent/src/agent.ts](https://github.com/earendil-works/pi/blob/f41f80466e30f21cdcd4d52aba4a2c2cb6ee3cc6/packages/agent/src/agent.ts) | prompt、continue、steer、followUp、abort、waitForIdle；活跃调用与队列区分，reset 不能污染运行中 transcript | 对话实例、取消令牌、显式 follow_up；steer 首期不开放 | P03/P05 |
| [agent/src/agent-loop.ts](https://github.com/earendil-works/pi/blob/f41f80466e30f21cdcd4d52aba4a2c2cb6ee3cc6/packages/agent/src/agent-loop.ts) | runLoop、streamAssistantResponse、prepareToolCall、executePreparedToolCall；工具结果回到下一轮 | 有界 loop + executor；不带 ORM | P03 |
| [agent/src/harness/skills.ts](https://github.com/earendil-works/pi/blob/f41f80466e30f21cdcd4d52aba4a2c2cb6ee3cc6/packages/agent/src/harness/skills.ts) | loadSkills/loadSourcedSkills、formatSkillInvocation、frontmatter 和诊断 | 审核目录 catalog、load_skill 工具、按需注入 | P07 |
| [agent/src/harness/compaction/compaction.ts](https://github.com/earendil-works/pi/blob/f41f80466e30f21cdcd4d52aba4a2c2cb6ee3cc6/packages/agent/src/harness/compaction/compaction.ts) | estimateContextTokens、findCutPoint、prepareCompaction、compact；摘要与保留尾部 | context_policy.py、compaction.py；保留历史 | P08 |
| [coding-agent/core/agent-session.ts](https://github.com/earendil-works/pi/blob/f41f80466e30f21cdcd4d52aba4a2c2cb6ee3cc6/packages/coding-agent/src/core/agent-session.ts) | 高层 prompt/Skill 调用、事件订阅、重试/压缩/abort 协调；不是 Agent Loop 本身 | conversation_service + 持久化 Runner | P04～P08 |
| [coding-agent/core/session-manager.ts](https://github.com/earendil-works/pi/blob/f41f80466e30f21cdcd4d52aba4a2c2cb6ee3cc6/packages/coding-agent/src/core/session-manager.ts) | SessionEntry、parentId、compaction entries、buildSessionContext、appendMessage、版本化会话文件 | MySQL Repository + schema_version；首期线性历史 | P04/P08 |
| [agent/src/index.ts](https://github.com/earendil-works/pi/blob/f41f80466e30f21cdcd4d52aba4a2c2cb6ee3cc6/packages/agent/src/index.ts) | 导出 core、harness、skills、compaction、session 等，说明当前分层不只在 coding-agent 包中 | 明确依赖方向，禁止工具层反向引用前端 | P01 |
| [LICENSE](https://github.com/earendil-works/pi/blob/f41f80466e30f21cdcd4d52aba4a2c2cb6ee3cc6/LICENSE) | MIT，Copyright (c) 2025 Mario Zechner | 翻译上游代码时保留声明并记录来源 | 全部 |

以上是 TestMind 的选择性映射，不是对每个上游模块的完整审计。没有读取全部 Provider 实现，不承诺全供应商兼容。

## 3. 真正要迁移的是行为，不是目录

Pi 的基本闭环允许模型不调用工具而直接回复；工具调用后生成对应结果消息，再交回模型。TestMind 的 conversation 模式必须遵守这个分离，而不是强行进入需求→覆盖→用例状态机。

重点差异：
- 上游有不受固定轮次约束的循环结构；TestMind 在每次物理模型调用/工具执行前检查预算和取消。
- 上游支持并行工具；TestMind 首期串行，避免 SQLAlchemy 会话共享与副作用顺序问题。
- 上游会话支持树/文件存储；TestMind 首期数据库线性会话，保留未来分支扩展但不建设 tree UI。
- 上游文件资源发现面更广；TestMind 只允许显式白名单资源根目录，禁用自动安装与脚本执行。
- beforeToolCall 可改变参数；TestMind 改后重新校验，防止绕过边界。
- 上游可能处理 thinking 内容；TestMind 不将隐藏推理保存为消息或展示。
- TestMind 的用户、项目权限、审批、Worker 租约、审计属于产品责任，不能从“使用 Pi 思路”推导已经安全。

## 4. 按上游测试提取行为样例

已检查 [agent-loop.test.ts](https://github.com/earendil-works/pi/blob/f41f80466e30f21cdcd4d52aba4a2c2cb6ee3cc6/packages/agent/test/agent-loop.test.ts)、[agent.test.ts](https://github.com/earendil-works/pi/blob/f41f80466e30f21cdcd4d52aba4a2c2cb6ee3cc6/packages/agent/test/agent.test.ts) 的测试名称和对应关键实现；尚未运行上游测试。

| 上游行为样例 | TestMind 验收样例 |
|---|---|
| transformContext 在 convertToLlm 前执行 | UI-only 事件先过滤，完整工具对再转换到 Provider |
| tool calls and results | call_id 不串配；工具结果可改变下一轮自然语言回复 |
| length-truncated assistant message 不执行工具 | 即使参数看似能解析也不能执行截断调用 |
| 工具完成顺序与结果持久化顺序区分 | 首期串行稳定；未来并行仍按原调用顺序重建模型上下文 |
| 参数预处理与 beforeToolCall | 类型校验、权限、审批逐层检查，修改后再校验 |
| 消息排队在合适边界处理 | follow_up 不制造同会话并行 Run；不撤销已完成动作 |
| await subscriber / waitForIdle | 关键结果落库成功后才发布可恢复的终态 |
| 工具结束后迟到 update 被忽略 | 取消、代次变化、租约丢失后不追加幽灵消息 |
| reset / prompt during processing | API 返回明确忙碌/队列语义，不破坏 transcript |
| shouldStopAfterTurn / terminating tool results | 明确预算和等待边界，不重复催促工具形成无限循环 |

测试目录已确认另有 skills.test.ts、sdk-skills.test.ts、agent-session-compaction.test.ts、agent-session-concurrent.test.ts。P07/P08 实施时还需阅读这些文件的具体测试正文；目录存在不等于已验证内容。

## 5. 移植记录与许可证

- 本次只产生规划，没有复制上游实现进入业务代码。
- 每个新模块若翻译上游实现，记录来源文件、commit、改动范围、行为差异和对应 Python 测试。
- 改编代码保留上游版权与 MIT 许可说明；后续提交相应第三方说明文件。
- 对外表述为“参考 Pi 架构的 Python TestAgent”，不称“Pi 官方 Python SDK”，不声称兼容 Pi 全部扩展。
- 前端仍为 React/JavaScript；“Python 实现”指服务端内核，不是把 Web UI 改写为 Python。
