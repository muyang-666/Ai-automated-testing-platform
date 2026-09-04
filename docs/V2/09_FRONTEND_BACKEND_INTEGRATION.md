# 新 V2 联调计划与运行边界

> 当前为计划，以下新对话功能尚未联调通过。旧 T08 的实际联调记录完整见
> [历史联调说明](../archive/PRE_PI_V2_2026-09-03/09_FRONTEND_BACKEND_INTEGRATION.md)。
> 不得将旧 Fake 用例生成通过，写成新 Pi 风格对话内核通过。

## 1. 分层验证

| 层次 | 环境 | 验证重点 |
|---|---|---|
| P01～P03 | 纯 Python + Fake Provider/Tool | 文本/工具循环、事件顺序、预算和取消 |
| P04～P05 | 临时 SQLite，外键 ON，真实 Repository/Worker | 幂等、串行、租约、持久化、Conversation 主路径接通与 Workflow 退役 |
| P06 | 独立开发入口 + Fake 模型 + 实际 HTTP/SSE/Worker | 持续聊天、流、重连、Tool activity |
| P07 | 同左 + Artifact Domain | 建 Artifact、Revision/Diff/Undo、conflict（确定性测试） |
| P08 | 同左 + Fake Provider 对话 | Agent 动态 read/add/edit/delete/move、8 类对话场景 |
| P09 | 同左 + 前端脑图/Diff | 同一 Artifact、Diff/Undo、刷新恢复、双浏览器冲突 |
| P10 | 经授权的测试 MySQL + 小额真实模型 | DDL/并发/供应商协议及真实延迟 |
| P10 | 现有回归套件 | 旧业务与新入口兼容 |

隔离入口不得更改正式登录依赖、读取真实 Key 或连接生产库。测试对话和 Skill 使用合成笔记/计算，不复用实习项目内容。

## 2. 当前可运行的兼容服务

目前仓库启动的仍是旧业务与 Workflow，不是新 V2 对话内核。参考旧运行方式：

~~~powershell
cd D:\Ai-test-assistant\backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8001
~~~

另开终端启动 Worker：

~~~powershell
cd D:\Ai-test-assistant\backend
..\.venv\Scripts\python.exe -m app.workers.agent_worker
~~~

前端在 frontend 下 npm run dev。不要为阅读源码执行这些命令：现有启动会建表/初始化，Worker 会消费排队任务，可能调用真实模型。
D:\pi 只读参考，不需要 npm install，不增加第四个 Node 后端服务。

## 3. 新路线联调故事

- 登录后无项目/无来源直接聊天，第二轮引用第一轮；
- 文本→一个纯工具→解释结果；普通回复不走 JSON 产物校验；
- 创建/打开 TestArtifact → “先列测试点”→ Agent 动态调用 Tool → 脑图实时出现节点 → Chat 给出解释；
- “锁定这里补边界”→ Diff 只影响该分支；“第二个不要”→ 删除上一轮新增的第二个节点；
- 人工在脑图编辑一条用例 → 生成新 Revision → Agent 下一轮读取最新版；
- 浏览器最小化/刷新/网络重连后消息 ID、游标、Artifact 与 Revision 一致；
- 模型空内容/截断/超时后明确诊断，Conversation 不关闭；
- Worker 不在线有预检提示，长模型调用不被误判失活；
- 取消、进程中断和重新发送不会重放已确认动作；
- 两个用户之间消息、工具结果、Artifact、摘要完全隔离。

每个故事记录真实命令、输入类型、运行环境、HTTP/事件结果和数据库副作用；不要写主观“看起来成功”。

## 4. 发布前必须补齐

agent_chat 的显式模型绑定、三服务启动脚本、Worker 健康检查、SSE 鉴权和游标、迁移说明及回滚边界。
模型能力以真实 Provider 结果验证。JSON 只是协议载体，Pi 架构不能自动解决旧模型配置/空响应问题。
旧业务数据孤立引用、V1 全量 migration 缺口仍是遗留问题，本次只重写计划，没有操作数据库。
