# V2-P04 会话持久化、并发与幂等阶段验收

日期：2026-09-04。结论：**P04 在临时 SQLite、真实 ORM/Repository/事务范围验收通过。**

## 交付能力

- `agent_sessions.mode` 区分 `legacy_workflow/conversation`。历史及旧入口明确创建 legacy；conversation 会话允许 `project_id=NULL`，owner 始终必填。
- AgentRun 复用为一次 ConversationTurn，`workflow_code=conversation`；`user_message_id` 关联首条用户消息，`active_slot=1` 的数据库唯一/检查约束保证同会话只有一个活跃 Turn。进入终态后清空槽位。
- `submit_conversation_turn` 在一个事务内写入 P01 UserMessage、queued Run、client_request_id 和 input_hash。相同键+相同正文返回原 Run/消息；相同键+不同正文稳定冲突；失败回滚消息、Run 和序号游标。
- AgentMessage 保存 P01 的稳定 message_id、schema_version、timestamp_ms 与完整 content_json。恢复时按 sequence_no 排序并重新经过 `parse_message`；损坏版本/ID 拒绝，工具调用和工具结果 ID 能完整往返。
- 消息和事件序号由 `agent_sessions.next_*_sequence` 的数据库原子 UPDATE 分配，不再使用 `max+1`。双连接验证不同消息取得 1/2，不靠 Python 全局锁。
- 旧读取路由对 conversation 只允许 owner，不能借项目读权限旁路；旧发送/用例生成入口拒绝 conversation 模式。旧 Worker 在 P05 接入分发前不会抢 conversation queued Run。

## 迁移

新增 head：`0003_conversation_persistence`，真实 down_revision 为 `0002_agent_platform_tables`。

- upgrade 将既有会话回填为 legacy，并根据已有消息/事件最大序号初始化下一序号；放宽 session/run project_id；增加模式、稳定消息字段、活跃槽、索引和约束。
- 新代码 `create_all` 先建 head 表的重叠场景会核对关键 nullable、唯一约束、check 和索引；部分列或不一致结构明确失败。
- downgrade 仅在没有 conversation/版本化消息数据时执行；发现 projectless 会话、conversation Run、message_id 等会拒绝，避免静默丢失数据。
- 为避免 agent_messages↔agent_runs 循环外键，user_message_id 由同事务服务校验归属；message.run_id 继续保留数据库外键。首次迁移测试产生的表排序 warning 因此消除。

## Pi 对照

固定提交 `f41f80466e30f21cdcd4d52aba4a2c2cb6ee3cc6`：`coding-agent/src/core/session-manager.ts` 的版本化消息 entry、appendMessage 和 buildSessionContext 提供“保存完整消息并按顺序重建”的行为依据。

TestMind 不复制 Pi 的 JSONL/树分支存储：现有产品已使用 SQLAlchemy/MySQL，因此以关系表保存 owner、Run、幂等键、稳定序号与 P01 JSON 合同。P04 保持线性历史；分支/压缩属 P08。改编说明继续保留 Pi MIT / Copyright (c) 2025 Mario Zechner。

## 测试证据

项目 `.venv`，仅临时/内存 SQLite，未连接真实 MySQL：

```text
P04 migration + conversation persistence
→ 20 passed, 14 warnings in 9.35s

P01 conversation contracts
→ 90 passed in 9.82s

P02 streaming providers
→ 54 passed, 13 warnings in 7.35s

P03 agent loop
→ 30 passed, 13 warnings in 3.93s

legacy services + API + models + Worker
→ 100 passed, 151 warnings in 10.98s
```

套件分别统计。warning 为既有 Pydantic、FastAPI on_event、SQLAlchemy Query.get 等弃用提示，本阶段没有为清理警告扩大范围。

P04 20 项包含 9 项迁移和 11 项持久化/并发测试：旧数据回填、upgrade/downgrade/re-upgrade、create_all 重叠校验、部分结构拒绝、有数据无损降级门禁、无项目会话、模式隔离、原子幂等、失败回滚、完整工具历史恢复、owner 隔离、相同/不同幂等请求双连接竞争、双连接序号、批量消息回滚以及旧 Worker 隔离。

并发扩测曾复现“第一次查幂等为空，另一事务随后提交，当前事务只看到活跃槽”的竞态；修正为活跃冲突前再次读取幂等键。该失败是开发证据，不计入最终通过数量。

## 阶段边界

P04 尚未运行真实 MySQL，也未接 Conversation Worker、租约/fencing、取消轮询、API/SSE/前端。conversation Run 会保持 queued，旧 Worker 被明确隔离；P05 才建立统一分发。P06 才提供正式对话接口。本轮未整理学习笔记。
