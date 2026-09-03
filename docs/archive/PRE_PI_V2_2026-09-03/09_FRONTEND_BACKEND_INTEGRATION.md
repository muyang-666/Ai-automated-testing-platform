# V2.1-T08 前后端联调与启动说明

> 2026-09-03；Codex 实施。主闭环已在隔离环境跑通，不代表真实供应商、MySQL 或 V2.1 发布验收完成。

## 1. 本次交付

前端复用现有 React / Ant Design / Axios，无新增依赖。全局悬浮 Agent 工作台支持最小化、恢复、最大化、标题栏拖动、右下角自由缩放；桌面保留位置和尺寸，小屏切换对话与产物视图。

需求管理、接口文档页保留原有生成入口，并增加“交给 Agent”。入口携带 projectId、sourceType、sourceId、sourceLabel；输入自然语言测试重点后启动已注册的 case_generation，不是任意聊天路由，也不是内嵌 Claude Code。

主流程：指定来源 → 发送目标 → 范围确认（类型/数量/重点可改）→ 覆盖计划确认（可取消计划项）→ 候选及覆盖结果 → 勾选保存。支持停止、拒绝审批、会话历史、刷新恢复、步骤/事件进度、假设和警告。只勾选保存的候选写入业务表。

## 2. 联调修正的合同

| 动作 | 实际 HTTP 合同 | 前端处理 |
|---|---|---|
| 创建会话 | POST /agent/sessions | project_id、title、context_json |
| 保存用户消息 | POST /agent/sessions/{id}/messages | 只传 content，不在该请求重复创建 Run |
| 启动生成 | POST /agent/runs/case-generation | 平铺 session_id、source_type、source_id、case_types、max_cases、user_goal、idempotency_key；202 |
| 会话恢复 | GET /agent/sessions/{id}；GET /agent/sessions/{id}/runs | 恢复消息、来源和最近 Run；新增 owner-only runs 查询 |
| 任务快照 | GET /agent/runs/{id}、/steps、/artifacts、/approvals；GET /agent/sessions/{id}/events | 新增 owner-only approvals 查询；当前 phase 匹配 pending 审批 |
| 范围/覆盖确认 | POST /agent/approvals/{id}/resolve | status + resolution_json，不再发送 decision/resolution |
| 保存候选 | POST /agent/runs/{id}/save-candidates | 仅 candidate_ids；后端重新校验产物和来源 |
| 停止 | POST /agent/runs/{id}/cancel | 补齐会话 owner 校验，项目读者不能取消其他人任务 |

保存 GATE 不允许通过通用 resolve 接口直接 approved；返回 409，必须调用 save-candidates，避免“审批成功但没有保存”的伪完成。

产物适配实际后端结构：候选业务字段在 candidates[].case 内；候选 ID 使用服务端外层 candidate_id。覆盖 matrix 为数组，生成前显示“尚未生成”，不把空矩阵显示成全部覆盖。保存后从 Approval.resolution_json 恢复已保存候选勾选状态。

## 3. 状态和错误处理

- queued/running 每 1.5 秒读取快照；waiting_approval/终态停止轮询。最小化不停止后端任务。
- 请求代次隔离旧响应，卸载清除定时器；新会话或切换来源不会被旧轮询覆盖。StrictMode 下可以恢复。
- 状态同步失败最多自动重试 3 次，然后显示错误并提供刷新；错误不得被下一次成功轮询静默清除。
- 写请求结束后先重新读取服务端状态；创建 Run 重试复用同一 idempotency_key。不自动重放保存或审批请求。
- 只在浏览器保存窗口布局和按用户隔离的最近会话 ID，不保存消息、产物或模型 Key。
- FastAPI 422 校验数组转换为文本；409 来源变化错误在窗口顶部显示，小屏也可见。
- 当前活跃/待审批任务结束前不切换会话，防止把审批或勾选提交给其他任务。

## 4. 可复现的隔离联调

以下入口仅供本地开发，不可部署。模型固定返回虚构数据；服务仅监听 loopback，用临时 SQLite、虚构用户、真实 Router / Service / Runtime / Worker。不会导入生产 app.main，不改正式鉴权，不读取或使用真实模型 Key，不访问业务接口。

在仓库根目录打开 PowerShell A：

```powershell
.\.venv\Scripts\python.exe backend\tests\manual\agent_preview_server.py
```

另开 PowerShell B：

```powershell
cd D:\Ai-test-assistant\frontend
$env:VITE_API_BASE_URL = 'http://127.0.0.1:8011'
npm run dev -- --host 127.0.0.1 --port 5175 --strictPort
```

浏览器打开 `http://127.0.0.1:5175/agent-integration.html`。该页面是独立开发入口，不进入默认生产构建。退出两个终端服务用 Ctrl+C；后端清理本次临时数据库。再次启动是空的新联调库，旧浏览器会话 ID 可能显示“会话不存在”，重新点击来源按钮即可。

强制终止进程可能跳过 Python finally 并留下临时目录；本次工具终止后，已核对并删除仅属于本次联调的两份 integration.sqlite3 及其临时目录，未触碰项目数据库。8011/5175 联调服务均已停止。

页面按钮“查询真实保存结果”读取临时库的 function_cases / api_cases，不是前端模拟成功。来源变更测试使用需求 #2，与正常需求 #1 隔离；生成候选后点击“修改隔离需求”，再保存应被拒绝。

Fake Gateway 只准备固定分析和生成结果，不覆盖自由修正；同一来源保存后重复生成可能因去重进入未配置的 repair，从而明确失败。需要重测 happy path 时重启隔离服务，不连接真实模型绕过。

## 5. 本次实际验证证据

### 自动检查

- `node --test tests/agentContract.test.mjs`（frontend）：6 passed。
- `python -m pytest tests/api/test_agent_api.py -q -k integration_`（backend，项目 venv）：2 passed，27 deselected；只运行新增针对性测试，未重跑全量后端测试。
- 针对新增前端目录/API/隔离入口/合同测试的 ESLint：exit 0。
- `npm run build`：通过；仍有大于 500 kB 的 bundle 警告，未以本任务进行全站分包重构。

### 浏览器真实 HTTP + Worker 验证

| 场景 | 观察结果 |
|---|---|
| 需求 happy path | 修改范围数量/类型，确认覆盖；生成 2 条、只选 1 条保存；查询临时库实际仅 1 条 FunctionCase |
| 接口 happy path | 同一 endpoint 的正常/异常 2 条场景均保留；保存后临时库实际 2 条 APICase |
| 生成前后覆盖 | 计划阶段不显示已覆盖；候选显示名称、步骤/预期、条款关联，API 显示代码生成检查但不声称执行测试 |
| 刷新恢复 | 会话、任务、消息、产物恢复；已保存候选保持勾选并不可再次修改 |
| 来源变化 | 保存返回拒绝原因；查询临时库 function_cases、api_cases 均为空；取消后可重新开始 |
| 会话/窗口 | 历史列表及切换；最小化/恢复、最大化、拖动、原生缩放和布局保持 |
| 小屏 | 390×844 页面宽度 390，无持续横向溢出；产物与对话可切换 |

## 6. 正式本地链路启动要点（未操作真实环境）

正常使用仍从原登录入口进入，API 默认 `http://127.0.0.1:8001`。除原 FastAPI 和 Vite 服务外，需要在使用同一数据库/模型配置的独立终端启动：

```powershell
cd D:\Ai-test-assistant\backend
..\.venv\Scripts\python.exe -m app.workers.agent_worker
```

数据库迁移必须先按 T02 规定完成；本说明不授权自动操作 MySQL 或执行 stamp。两个场景 requirement_to_function_case、api_doc_to_api_case 必须配置可用模型。缺少 Worker 时页面会一直 queued，并提示检查 Worker。

如果前端终端之前运行过隔离入口，先在该终端移除仅为联调设置的变量，再重启正常前端：`Remove-Item Env:VITE_API_BASE_URL`。不要把 8011 的 fixture 当正式服务。

## 7. 尚未验收的边界

- 真实供应商输出、时延与成本；真实 MySQL 迁移/并发；正式登录和项目权限下整页业务流程，仍需指定测试环境验证。
- 多 Skill 自然语言路由、自由对话局部 refine、候选直接编辑没有后端合同；不放置假按钮，不声称实现。当前可编辑范围和覆盖计划。
- 自动模型 repair 已有 T06 实现，但本次手动浏览器联调不覆盖真实 repair 输出质量。
- 会话目前恢复最近 Run，不能在同一会话中选择任意历史 Run；消息/事件读取有后端条数上限，长期大容量分页待优化。
- 时间字段沿用后端当前序列化；UTC 时区合同、独立 Worker 心跳等既有边界未在此扩展。
- T09 影子评测、V1 全量回归和发布门禁未执行；V2.1 不能仅凭本次联调标记发布完成。

## 8. V2.1-T08.1 会话创建校验（正式环境 500 修复）

创建会话 `POST /agent/sessions` 在插入前按序校验，外键仍保留为最终约束：

1. 项目必须存在、未删除且状态为 active → 否则 404 `项目不存在或已删除…` / 400 `项目状态为…`；
2. 项目内可操作权限（沿用现有 `require_project_write` 语义）→ 无权限 403；
3. 若携带来源（`context_json.source_type/source_id`）：来源存在、未删除且归属项目与请求一致 → 否则 404 `…不存在或已删除…`、400 `…与所选项目不一致…`；无来源上下文的合法会话不受影响；
4. 竞态等导致 FK 失败时回滚并返回稳定 409，不再暴露 500。

前端 `useAgentSession.send()` 创建会话遇 4xx（项目/来源失效或无权）会：终止后续 Message/Run、清空本次来源上下文并显示可操作提示（`sessionStartErrorText`，引导回到需求/接口文档页重新“交给 Agent”）；不清除服务端历史会话。真实 MySQL `ai_test_assistant` 的 `projects` 表当前为 0 行而 `requirement_docs` 1、2 引用 project_id=2，是历史孤立数据，需用户决策处置后原需求才能正常生成（详见开发记录第 19 节）。

