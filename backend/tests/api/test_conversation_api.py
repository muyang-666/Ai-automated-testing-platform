"""P06 Conversation API 测试（TestClient + SQLite + 依赖覆盖；Fake Provider/Worker）。

覆盖提示词 §24 场景 1-20：创建/owner/list/跨用户、turn/follow_up/reject/幂等、
messages 游标与结构化内容、queue_state、conversation cancel 语义、SSE auth/跨用户/
游标续传去重、Fake 文本/工具/provider error、refresh snapshot 一致性。不使用真实 LLM。
"""
import asyncio
import json
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.agents.conversation.budget import AgentLoopLimits
from app.agents.conversation.events import AssistantDoneEvent, AssistantErrorEvent, AssistantStartEvent
from app.agents.conversation.messages import AssistantMessage, TextContent, ToolCall, Usage
from app.agents.conversation.runner import ConversationRunner
from app.agents.providers.streaming import AttemptBudget, ProviderSnapshot
from app.agents.registry.tool_registry import ToolRegistry
from app.core.database import SessionLocal
from app.main import app
from app.models.agent.agent_event import AgentEvent
from app.models.agent.agent_run import AgentRun
from app.models.user import User
from app.routers.dependencies import get_current_user
from app.services.agent import agent_run_service, conversation_service
from app.services.agent.conversation_service import submit_conversation_turn
from app.workers.agent_worker import AgentWorker

USER_A_ID = 101
USER_B_ID = 202


def usage():
    return Usage(input=1, output=1, cache_read=None, cache_write=None,
                 total_tokens=2, cost=None)


def chat_reply(text):
    return AssistantMessage(message_id="template", timestamp=1, role="assistant",
        content=[TextContent(text=text)], api="chat", provider="fake", model="fake-model",
        usage=usage(), stop_reason="stop")


class ScriptedGateway:
    def __init__(self, responses, slow_seconds=0.0):
        self.responses = list(responses)
        self.slow_seconds = slow_seconds
        self.requests = []
        self.aborted = False

    def stream(self, snapshot, request, *, context, control, limits=None):
        self.requests.append(request)
        final = self.responses.pop(0).model_copy(deep=True, update={
            "message_id": context.message_id, "timestamp": context.timestamp})

        @asynccontextmanager
        async def managed():
            async def events():
                partial = final.model_copy(deep=True, update={"content": [], "stop_reason": "pending"})
                yield AssistantStartEvent(partial=partial)
                deadline = time.monotonic() + self.slow_seconds
                while time.monotonic() < deadline:
                    if control.cancel_event.is_set():
                        self.aborted = True
                        control.error_code = "canceled"
                        error = chat_reply("").model_copy(deep=True, update={
                            "message_id": context.message_id, "timestamp": context.timestamp,
                            "content": [], "stop_reason": "aborted"})
                        yield AssistantErrorEvent(reason="aborted", error=error)
                        return
                    await asyncio.sleep(0.005)
                if final.stop_reason in {"error", "aborted"}:
                    control.error_code = getattr(control, "error_code", None) or "synthetic_model_error"
                    yield AssistantErrorEvent(reason=final.stop_reason, error=final)
                else:
                    yield AssistantDoneEvent(reason=final.stop_reason, message=final)
            yield events()
        return managed()


_API_ID_SEQ = iter(f"x{i}" for i in range(1, 1000000))


class RunnerAdapter:
    def __init__(self, gateway):
        self.gateway = gateway
        self._runner = ConversationRunner(
            gateway=gateway,
            snapshot=ProviderSnapshot("openai_compatible", "fake", "https://fake.invalid",
                                      "key", "fake-model", max_tokens=20),
            tool_registry=_tools_with_calculator(),
            system_prompt="be helpful",
            limits=AgentLoopLimits(),
            provider_attempt_budget=AttemptBudget(limit=20),
            id_factory=lambda: next(_API_ID_SEQ),  # 跨 Run 唯一，避免 message_id 碰撞
            timestamp_factory=lambda: int(time.time() * 1000),
        )

    async def run(self, db, run_id, cancel_event=None, **kwargs):
        persister = getattr(self, "event_persister", None)
        if persister is not None:
            self._runner.event_persister = persister
        return await self._runner.run(db, run_id, cancel_event=cancel_event, **kwargs)


def _tools_with_calculator() -> ToolRegistry:
    from app.agents.tools.conversation_safe_tools import build_conversation_tool_registry
    return build_conversation_tool_registry()


def make_runner_factory(gateways):
    created = []

    def factory():
        gateway = gateways.pop(0)
        created.append(gateway)
        return RunnerAdapter(gateway)

    return factory, created


def make_worker(factory, created=None):
    return AgentWorker(
        session_factory=SessionLocal,
        runtime_factory=lambda hook: None,
        worker_id="api-worker",
        poll_interval_seconds=0.1,
        stale_after_seconds=5.0,
        conversation_runner_factory=factory,
        heartbeat_interval_seconds=0.02,
        heartbeat_failure_limit=1,
    )


def make_worker_standalone(gateway):
    """不依赖工厂 pop 的 worker（供单次 run）。"""
    holder = {}

    def factory():
        holder["gateway"] = gateway
        return RunnerAdapter(gateway)

    return make_worker(factory), holder


def seed_users(db):
    db.add(User(id=USER_A_ID, username="user-a", password_hash="x", salt="y",
                status="active", is_deleted=False))
    db.add(User(id=USER_B_ID, username="user-b", password_hash="x", salt="y",
                status="active", is_deleted=False))
    db.commit()


@pytest.fixture()
def client(db_session):
    seed_users(db_session)
    app.dependency_overrides[get_current_user] = lambda: db_session.get(User, USER_A_ID)
    yield TestClient(app)
    app.dependency_overrides.pop(get_current_user, None)


def switch_user(user_id):
    app.dependency_overrides[get_current_user] = lambda: None or _user_lookup(user_id)


def _user_lookup(user_id):
    db = SessionLocal()
    try:
        return db.get(User, user_id)
    finally:
        db.close()


def create(client, title="聊天", project_id=None):
    return client.post("/agent/conversations",
                       json={"title": title, "project_id": project_id})


# ---------------------------------------------------------------- 1-9：CRUD/Turn/Queue

def test_create_list_snapshot_and_turn_contracts(client, db_session):
    created = create(client, title="无项目聊天")
    assert created.status_code == 201
    cid = created.json()["id"]
    assert created.json()["project_id"] is None

    listed = client.get("/agent/conversations")
    assert listed.status_code == 200
    assert [row["id"] for row in listed.json()] == [cid]

    submitted = client.post(f"/agent/conversations/{cid}/turns", json={
        "content": "你好", "client_request_id": "req-1", "queue_mode": "follow_up"})
    assert submitted.status_code == 202
    body = submitted.json()
    assert body["queue_state"] in {"executable", "idle"} and body["replayed"] is False

    # 幂等 replay
    replayed = client.post(f"/agent/conversations/{cid}/turns", json={
        "content": "你好", "client_request_id": "req-1", "queue_mode": "follow_up"})
    assert replayed.status_code == 202 and replayed.json()["replayed"] is True
    assert replayed.json()["run_id"] == body["run_id"]

    # 同 key 不同内容 409
    conflict = client.post(f"/agent/conversations/{cid}/turns", json={
        "content": "不同内容", "client_request_id": "req-1", "queue_mode": "follow_up"})
    assert conflict.status_code == 409

    detail = client.get(f"/agent/conversations/{cid}")
    assert detail.status_code == 200
    snap = detail.json()
    assert snap["queue_state"] in {"executable", "idle"}
    assert snap["latest_message_sequence"] >= 1


def test_cross_user_access_isolated(client, db_session):
    created = create(client)
    cid = created.json()["id"]
    switch_user(USER_B_ID)
    assert client.get(f"/agent/conversations/{cid}").status_code == 404
    assert client.get(f"/agent/conversations/{cid}/messages").status_code == 404
    assert client.get("/agent/conversations").json() == []
    assert client.get(f"/agent/conversations/{cid}/events").status_code == 404
    # B 不能对 A 的 run cancel / 也不能投递 turn
    switch_user(USER_A_ID)
    submitted = client.post(f"/agent/conversations/{cid}/turns", json={
        "content": "hi", "client_request_id": "req-x", "queue_mode": "reject"})
    run_id = submitted.json()["run_id"]
    switch_user(USER_B_ID)
    assert client.post(f"/agent/conversation-runs/{run_id}/cancel").status_code == 404
    assert client.post(f"/agent/conversations/{cid}/turns", json={
        "content": "x", "client_request_id": "b1"}).status_code == 404


def test_follow_up_and_reject_queue_modes(client, db_session):
    cid = create(client).json()["id"]
    first = client.post(f"/agent/conversations/{cid}/turns", json={
        "content": "A", "client_request_id": "a1", "queue_mode": "follow_up"}).json()
    # A 置 running（模拟 Worker claim）
    agent_run_service.claim_queued_run(db_session, first["run_id"], "api-worker",
                                       datetime.utcnow())
    db_session.commit()

    follow = client.post(f"/agent/conversations/{cid}/turns", json={
        "content": "B", "client_request_id": "b1", "queue_mode": "follow_up"})
    assert follow.status_code == 202
    assert follow.json()["queue_state"] in {"executable", "paused", "idle"}
    reject = client.post(f"/agent/conversations/{cid}/turns", json={
        "content": "C", "client_request_id": "c1", "queue_mode": "reject"})
    assert reject.status_code == 409
    snap = client.get(f"/agent/conversations/{cid}").json()
    assert snap["queued_follow_ups"] == 1


def test_messages_after_sequence_structured(client, db_session):
    cid = create(client).json()["id"]
    submitted = client.post(f"/agent/conversations/{cid}/turns", json={
        "content": "hi", "client_request_id": "m1"}).json()
    run_id = submitted["run_id"]
    # 手动持久化一条带 ToolCall 的助手消息与 ToolResult（模拟 Agent 结果）
    call = AssistantMessage(message_id="call-1", timestamp=11, role="assistant",
        content=[TextContent(text="calling"), ToolCall(id="tc1", name="calculator",
                                                       arguments={"operation": "add", "left": "1", "right": "2"})],
        api="chat", provider="fake", model="m", usage=usage(), stop_reason="toolUse")
    result_msg = _tool_result("tc1", "3")
    conversation_service.persist_conversation_messages(
        db_session, session_id=cid, requester_user_id=USER_A_ID, run_id=run_id,
        messages=[call, result_msg])

    page1 = client.get(f"/agent/conversations/{cid}/messages").json()
    assert [row["role"] for row in page1] == ["user", "assistant", "toolResult"]
    assert page1[1]["content"][1]["type"] == "toolCall"
    assert page1[2]["content"][0]["text"] == "3"
    after = client.get(f"/agent/conversations/{cid}/messages",
                       params={"after_sequence": page1[0]["sequence_no"]}).json()
    assert [row["role"] for row in after] == ["assistant", "toolResult"]


def _tool_result(call_id, text):
    from app.agents.conversation.messages import ToolResultMessage
    return ToolResultMessage(message_id=f"tr-{call_id}", timestamp=12, role="toolResult",
                             tool_call_id=call_id, tool_name="calculator",
                             content=[TextContent(text=text)], is_error=False)


# ---------------------------------------------------------------- 10-12：cancel

def test_cancel_running_head_and_follow_up_cancel(client, db_session):
    cid = create(client).json()["id"]
    head = client.post(f"/agent/conversations/{cid}/turns", json={
        "content": "A", "client_request_id": "ca1"}).json()
    agent_run_service.claim_queued_run(db_session, head["run_id"], "api-worker",
                                       datetime.utcnow())
    db_session.commit()
    b = client.post(f"/agent/conversations/{cid}/turns", json={
        "content": "B", "client_request_id": "ca2", "queue_mode": "follow_up"}).json()
    c = client.post(f"/agent/conversations/{cid}/turns", json={
        "content": "C", "client_request_id": "ca3", "queue_mode": "follow_up"}).json()

    # queued follow-up cancel：只取消 B，不 promote C（head A 仍在 running）
    b_cancel = client.post(f"/agent/conversation-runs/{b['run_id']}/cancel", json={})
    assert b_cancel.status_code == 200
    assert db_session.get(AgentRun, b["run_id"]).status == "cancelled"
    assert db_session.get(AgentRun, head["run_id"]).status == "running"
    assert db_session.get(AgentRun, c["run_id"]).status == "queued"
    assert db_session.get(AgentRun, c["run_id"]).active_slot is None  # 未被错误 promote

    # 取消 running head → cancelled
    head_cancel = client.post(f"/agent/conversation-runs/{head['run_id']}/cancel", json={})
    assert head_cancel.status_code == 200
    body = head_cancel.json()
    assert body["status"] == "cancelled"


def test_queued_head_cancel_promotes_next(client, db_session):
    """Preflight 场景：A queued head 在 Worker claim 前被 cancel → B promoted。"""
    cid = create(client).json()["id"]
    a = client.post(f"/agent/conversations/{cid}/turns", json={
        "content": "A", "client_request_id": "qh1"}).json()
    b = client.post(f"/agent/conversations/{cid}/turns", json={
        "content": "B", "client_request_id": "qh2", "queue_mode": "follow_up"}).json()
    # A 仍是 queued（未被 claim）
    assert db_session.get(AgentRun, a["run_id"]).status == "queued"
    cancelled = client.post(f"/agent/conversation-runs/{a['run_id']}/cancel", json={})
    assert cancelled.status_code == 200
    snap = client.get(f"/agent/conversations/{cid}").json()
    assert snap["active_run"]["id"] == b["run_id"]
    assert snap["active_run"]["status"] == "queued"
    assert snap["queued_follow_ups"] == 0
    assert db_session.get(AgentRun, a["run_id"]).status == "cancelled"


# ---------------------------------------------------------------- 13-16：SSE

def test_sse_auth_required(client):
    app.dependency_overrides.pop(get_current_user, None)
    try:
        response = client.get("/agent/conversations/1/events")
        assert response.status_code in (401, 403)
    finally:
        app.dependency_overrides[get_current_user] = lambda: _user_lookup(USER_A_ID)


def test_sse_cursor_reconnect_and_duplicate_protection(client, db_session, monkeypatch):
    cid = create(client).json()["id"]
    run_id = client.post(f"/agent/conversations/{cid}/turns", json={
        "content": "hi", "client_request_id": "sse1"}).json()["run_id"]
    # 手动造事件（模拟 Worker 已写）
    with SessionLocal() as db:
        agent_run_service.append_event(db, cid, run_id, "run_started", {})
        agent_run_service.append_event(db, cid, run_id, "run_succeeded", {})
        db.commit()

    # SSE must not retain the request Session/transaction for its full lifetime.
    # Count the short polling Sessions used by the generator.
    import app.routers.agent.conversation_router as conversation_router_module
    poll_sessions = []

    def short_session_factory():
        session = SessionLocal()
        poll_sessions.append(session)
        return session

    monkeypatch.setattr(conversation_router_module, "SessionLocal", short_session_factory)

    def read_events(after=None):
        params = {"timeout_seconds": 3}
        if after is not None:
            params["after_sequence"] = after
        with client.stream("GET", f"/agent/conversations/{cid}/events", params=params) as response:
            assert response.status_code == 200
            lines = [line if isinstance(line, str) else line.decode()
             for line in response.iter_lines() if line]
        events = [json.loads(line.split("data: ", 1)[1]) for line in lines if line.startswith("data: ")]
        return events

    first = read_events()
    assert [e["event_type"] for e in first] == ["run_started", "run_succeeded"]
    assert len(poll_sessions) > 1  # 每轮新建短 Session，避免 MySQL 重复读快照
    cursor = first[-1]["sequence_no"]
    # 断线重连 from cursor：无重复
    second = read_events(after=cursor)
    assert second == []
    # 新事件出现在 cursor 之后
    with SessionLocal() as db:
        agent_run_service.append_event(db, cid, run_id, "run_failed", {})
        db.commit()
    third = read_events(after=cursor)
    assert [e["event_type"] for e in third] == ["run_failed"]


# ---------------------------------------------------------------- 17-20：E2E Fake Worker/SSE 集成

def test_full_http_worker_stream_story_with_calculator(client, db_session):
    """§26 验收故事（无 HTTP 限制外皆走真实 HTTP+Worker+Fake Provider）。"""
    cid = create(client).json()["id"]

    def respond():
        assistant_with_tool = chat_reply("calling").model_copy(deep=True, update={
            "message_id": "reply-1", "content": [ToolCall(id="c1", name="calculator",
                                                          arguments={"operation": "add",
                                                                     "left": "17", "right": "5"})],
            "stop_reason": "toolUse"})
        return [assistant_with_tool, chat_reply("22")]

    # Turn 1：记住数字
    first = client.post(f"/agent/conversations/{cid}/turns", json={
        "content": "记住数字 17", "client_request_id": "story1"}).json()
    worker, _ = make_worker_standalone(ScriptedGateway([chat_reply("好的")]))
    assert worker.run_once().action == "completed"

    # Turn 2：把它加 5 → calculator → 22
    second = client.post(f"/agent/conversations/{cid}/turns", json={
        "content": "把它加 5", "client_request_id": "story2"}).json()
    assert second["run_id"] != first["run_id"]
    worker2, holder = make_worker_standalone(ScriptedGateway(respond()))
    assert worker2.run_once().action == "completed"

    # refresh：messages 完整恢复（结构化 ToolCall 关联）
    messages = client.get(f"/agent/conversations/{cid}/messages").json()
    roles = [row["role"] for row in messages]
    assert roles.count("user") == 2 and roles.count("assistant") >= 3
    text = " ".join(str(row["content"]) for row in messages if row["role"] == "assistant")
    assert "22" in text

    # SSE 已持久化运行期事件（含 tool 生命周期与 message committed）
    with SessionLocal() as db:
        rows = db.query(AgentEvent).filter(
            AgentEvent.session_id == cid).order_by(AgentEvent.sequence_no.asc()).all()
        types = [row.event_type for row in rows]
    assert "conversation_tool_started" in types
    assert "conversation_tool_finished" in types
    assert "conversation_message_committed" in types
    assert "run_succeeded" in types

    # Turn 3：refresh 后继续问最初数字
    third = client.post(f"/agent/conversations/{cid}/turns", json={
        "content": "我刚才最开始给你的数字是什么？", "client_request_id": "story3"}).json()
    worker3, _ = make_worker_standalone(ScriptedGateway([chat_reply("17")]))
    assert worker3.run_once().action == "completed"
    tail = client.get(f"/agent/conversations/{cid}/messages",
                      params={"after_sequence": messages[-1]["sequence_no"]}).json()
    assert any(row["role"] == "assistant" and "17" in str(row["content"]) for row in tail)


def test_provider_error_snapshot_consistency(client, db_session):
    cid = create(client).json()["id"]
    client.post(f"/agent/conversations/{cid}/turns", json={
        "content": "boom", "client_request_id": "perr"}).json()
    error_message = chat_reply("").model_copy(deep=True, update={
        "content": [], "stop_reason": "error", "message_id": "e1"})
    worker, _ = make_worker_standalone(ScriptedGateway([error_message]))
    assert worker.run_once().action == "completed"  # runner 收敛为 failed outcome

    snap = client.get(f"/agent/conversations/{cid}").json()
    assert snap["active_run"] is None  # failed 已清 active_slot
    assert snap["head_status"] == "failed"
    assert snap["latest_run"]["status"] == "failed"
    assert snap["latest_run"]["error_code"] == "synthetic_model_error"
    assert snap["queue_state"] == "idle"  # 无 follow-up 时不误报 paused
    # refresh snapshot 一致性：messages 与 run 终态一致
    messages = client.get(f"/agent/conversations/{cid}/messages").json()
    assert messages[0]["role"] == "user"
    assert messages[-1]["role"] == "assistant"
    assert messages[-1]["stop_reason"] == "error"
    assert messages[-1]["error_code"] == "synthetic_model_error"


def test_capabilities_no_secret(client):
    response = client.get("/agent/conversation-capabilities")
    assert response.status_code == 200
    body = response.json()
    assert body["tools"] == ["calculator"]
    assert "api_key" not in body and "secret" not in json.dumps(body).lower()
    assert body["model_ready"] is False  # 测试库未配置 agent_chat 场景


def test_sse_does_not_reacquire_request_connection_after_rollback(db_session):
    from app.routers.agent.conversation_router import stream_events

    seed_users(db_session)
    chat = conversation_service.create_conversation_session(
        db_session, requester_user_id=USER_A_ID, title="stream connection",
    )
    db_session.commit()
    chat_id = chat.id
    user = db_session.get(User, USER_A_ID)
    response = stream_events(
        chat_id, after_sequence=0, timeout_seconds=1,
        db=db_session, current_user=user,
    )
    assert response.media_type == "text/event-stream"
    assert not db_session.in_transaction(), "SSE 持有请求级连接会挤占发送/刷新所需连接"
