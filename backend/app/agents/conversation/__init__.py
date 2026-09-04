"""V2 对话内核（conversation）包。

- messages.py：TextContent/ToolCall/Usage/UsageCost/StopReason/DeferredHandle
  与 UserMessage/AssistantMessage/ToolResultMessage 联合（V2-P01-01～03）；
- events.py：两层事件（AssistantMessageEvent / AgentEvent）及应用层外壳；
- contracts.py：ConversationTurn / ModelTurn 最小纯元数据；
- loop.py：纯 Python 有界 Agent Loop，组合 P02 模型流与串行工具结果反馈；
- tool_executor.py：工具参数重校验、策略门禁、串行执行和结果构造；
- budget.py / policy.py：逻辑轮次硬限额与默认只读工具策略；
- tool_validation.py：工具参数纯校验与 ToolResultMessage 纯构造（不执行）。

本包保证：导入不触发数据库、配置或网络客户端初始化，也不读取任何密钥。
"""
