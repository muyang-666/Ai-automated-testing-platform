"""P08 eight scripted Agent conversations through the real Runner/Loop/Tools."""
import asyncio
import itertools
from contextlib import asynccontextmanager

import pytest

from app.agents.conversation.events import AssistantDoneEvent, AssistantStartEvent
from app.agents.conversation.messages import AssistantMessage, TextContent, ToolCall, Usage
from app.agents.conversation.runner import ConversationRunner
from app.agents.providers.streaming import AttemptBudget, ProviderSnapshot
from app.agents.tools.artifacts.policy import ArtifactToolPolicy
from app.agents.tools.artifacts.runtime import build_artifact_runtime_context
from app.agents.tools.conversation_safe_tools import (
    build_conversation_system_prompt, build_conversation_tool_registry,
)
from app.core.database import SessionLocal
from app.models.test_artifact.artifact_node import ArtifactNode
from app.models.user import User
from app.services.agent import conversation_service
from app.services.test_artifacts import artifact_service

USER_ID = 8201


def _usage():
    return Usage(input=1, output=1, cache_read=None, cache_write=None,
                 total_tokens=2, cost=None)


def _assistant(message_id, blocks, reason="toolUse"):
    return AssistantMessage(message_id=message_id, timestamp=1, role="assistant",
        content=blocks, api="chat", provider="fake", model="scripted",
        usage=_usage(), stop_reason=reason)


def _call(message_id, call_id, name, arguments):
    return _assistant(message_id, [ToolCall(id=call_id, name=name, arguments=arguments)])


def _final(message_id="final", text="完成"):
    return _assistant(message_id, [TextContent(text=text)], "stop")


class ScriptedGateway:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def stream(self, snapshot, request, *, context, control, limits=None):
        del snapshot, control, limits
        self.requests.append(request)
        template = self.responses.pop(0)
        final = template.model_copy(deep=True, update={
            "message_id": context.message_id, "timestamp": context.timestamp,
        })

        @asynccontextmanager
        async def managed():
            async def events():
                yield AssistantStartEvent(partial=final.model_copy(
                    deep=True, update={"content": [], "stop_reason": "pending"}))
                yield AssistantDoneEvent(reason=final.stop_reason, message=final)
            yield events()
        return managed()


@pytest.fixture()
def world(db_session):
    user = User(id=USER_ID, username="p08-agent", password_hash="x", salt="y",
                status="active", is_deleted=False)
    db_session.add(user)
    db_session.commit()
    artifact = artifact_service.create_artifact(db_session, requester=user, title="登录测试")
    session = conversation_service.create_conversation_session(
        db_session, requester_user_id=USER_ID, title="P08 Agent",
    )
    db_session.commit()
    conversation_service.focus_conversation_artifact(
        db_session, session_id=session.id, artifact_id=artifact.id, requester=user,
    )
    db_session.commit()
    return user, artifact, session


def _run(db, session, responses, *, text, key, workspace_context=None):
    submission = conversation_service.submit_conversation_turn(
        db, session_id=session.id, requester_user_id=USER_ID, content=text,
        client_request_id=key, message_id_factory=lambda: f"user-{key}",
        timestamp_ms_factory=lambda: 1, workspace_context=workspace_context,
    )
    gateway = ScriptedGateway(responses)
    ids = itertools.count(1)
    runner = ConversationRunner(
        gateway=gateway,
        snapshot=ProviderSnapshot("openai_compatible", "fake", "https://fake.invalid",
                                  "key", "scripted", max_tokens=200),
        tool_registry=build_conversation_tool_registry(),
        system_prompt=build_conversation_system_prompt(), policy=ArtifactToolPolicy(),
        provider_attempt_budget=AttemptBudget(limit=20),
        application_context_factory=lambda **values: build_artifact_runtime_context(
            SessionLocal, **values),
        id_factory=lambda: f"{key}-{next(ids)}", timestamp_factory=lambda: 2,
    )
    outcome = asyncio.run(runner.run(db, submission.run.id))
    assert outcome.status == "succeeded" and not gateway.responses
    return gateway


def _apply(db, artifact, user, operations):
    result = artifact_service.apply_operations(db, artifact_id=artifact.id,
        expected_revision=artifact.current_revision, operations=operations, requester=user)
    db.commit()
    db.refresh(artifact)
    return result


def _nodes(db, artifact_id):
    db.expire_all()
    return db.query(ArtifactNode).filter(
        ArtifactNode.artifact_id == artifact_id, ArtifactNode.deleted_revision.is_(None),
    ).order_by(ArtifactNode.id).all()


def _case(title, tags=None):
    return {"operation_type": "add_node", "node_type": "test_case", "title": title,
            "content": {"preconditions": [], "steps": [{"action": "执行", "data": None}],
                        "expected_results": ["结果可观察"], "priority": "P2", "tags": tags or []}}


def test_1_empty_artifact_adds_test_points_only(world, db_session):
    user, artifact, session = world
    _run(db_session, session, [
        _call("m1", "c1", "get_current_artifact", {}),
        _call("m2", "c2", "batch_apply_artifact_operations", {"expected_revision": 1,
            "summary": "列出登录测试点", "operations": [
                {"operation_type": "add_node", "parent_id": artifact.root_node_id,
                 "node": {"node_type": "module", "title": "正常登录"}},
                {"operation_type": "add_node", "parent_id": artifact.root_node_id,
                 "node": {"node_type": "module", "title": "账号锁定"}},
            ]}), _final()], text="先列登录测试点，不展开用例", key="s1")
    nodes = _nodes(db_session, artifact.id)
    assert [node.node_type for node in nodes].count("module") == 2
    assert not any(node.node_type == "test_case" for node in nodes)
    assert _revision(db_session, artifact, user) == 2


def _revision(db, artifact, user):
    return artifact_service.get_artifact(db, artifact_id=artifact.id, requester=user).current_revision


def test_2_expands_only_selected_branch_in_one_revision(world, db_session):
    user, artifact, session = world
    _apply(db_session, artifact, user, [
        {"operation_type": "add_node", "parent_id": artifact.root_node_id,
         "node_type": "module", "title": "账号锁定", "ref": "lock"},
        {"operation_type": "add_node", "parent_id": artifact.root_node_id,
         "node_type": "module", "title": "其他分支"},
    ])
    lock = db_session.query(ArtifactNode).filter(ArtifactNode.title == "账号锁定").one()
    operations = []
    for index in range(3):
        item = _case(f"锁定边界 {index + 1}", ["边界"])
        item["parent_id"] = lock.id
        operations.append({"operation_type": "add_node", "parent_id": lock.id,
                           "node": {k: item[k] for k in ("node_type", "title", "content")}})
    _run(db_session, session, [
        _call("m1", "c1", "read_artifact_nodes", {"node_ids": [lock.id]}),
        _call("m2", "c2", "batch_apply_artifact_operations",
              {"expected_revision": 2, "operations": operations}), _final(),
    ], text="锁定这里补三个边界用例", key="s2")
    cases = [node for node in _nodes(db_session, artifact.id) if node.node_type == "test_case"]
    assert len(cases) == 3 and {node.parent_id for node in cases} == {lock.id}
    assert _revision(db_session, artifact, user) == 3


def test_3_minimal_edit_changes_only_requested_node(world, db_session):
    user, artifact, session = world
    op1 = _case("TC003"); op1["parent_id"] = artifact.root_node_id
    op2 = _case("TC004"); op2["parent_id"] = artifact.root_node_id
    _apply(db_session, artifact, user, [op1, op2])
    tc3, tc4 = [node for node in _nodes(db_session, artifact.id) if node.node_type == "test_case"]
    before4 = artifact_service.node_snapshot(tc4)
    _run(db_session, session, [
        _call("m1", "c1", "read_artifact_nodes", {"node_ids": [tc3.id]}),
        _call("m2", "c2", "update_artifact_node", {"expected_revision": 2,
            "target_node_id": tc3.id, "patch": {"content": {
                "preconditions": [], "steps": [{"action": "等待30分钟", "data": None}],
                "expected_results": ["锁定30分钟后允许重新登录"], "priority": "P1", "tags": ["边界"]}}}),
        _final(),
    ], text="把 TC003 预期改一下", key="s3")
    assert db_session.get(ArtifactNode, tc3.id).content_json["expected_results"] == [{"step_no": None, "expected": "锁定30分钟后允许重新登录"}]
    assert artifact_service.node_snapshot(db_session.get(ArtifactNode, tc4.id)) == before4
    diff = artifact_service.get_diff(db_session, artifact_id=artifact.id, from_revision=2,
                                     to_revision=3, requester=user)
    assert [change["node_id"] for change in diff["changes"]] == [tc3.id]


def test_4_second_one_uses_recent_diff_and_deletes_correct_node(world, db_session):
    user, artifact, session = world
    ops = []
    for title in ("TC021", "TC022", "TC023"):
        item = _case(title); item["parent_id"] = artifact.root_node_id; ops.append(item)
    _apply(db_session, artifact, user, ops)
    cases = [node for node in _nodes(db_session, artifact.id) if node.node_type == "test_case"]
    _run(db_session, session, [
        _call("m1", "c1", "get_artifact_diff", {"revision_count": 1}),
        _call("m2", "c2", "delete_artifact_node", {"expected_revision": 2,
                                                     "target_node_id": cases[1].id}),
        _final(),
    ], text="第二个不要", key="s4")
    visible = {node.title for node in _nodes(db_session, artifact.id)}
    assert "TC022" not in visible and {"TC021", "TC023"} <= visible


def test_5_moves_node_after_reading_relevant_nodes(world, db_session):
    user, artifact, session = world
    _apply(db_session, artifact, user, [
        {"operation_type": "add_node", "parent_id": artifact.root_node_id,
         "node_type": "module", "title": "原分支", "ref": "old"},
        {"operation_type": "add_node", "parent_id": artifact.root_node_id,
         "node_type": "module", "title": "账号锁定", "ref": "lock"},
        {"operation_type": "add_node", "parent_id": "@old", "node_type": "test_case",
         "title": "TC003", "content": _case("x")["content"]},
    ])
    old, lock, case = [node for node in _nodes(db_session, artifact.id) if node.node_type != "root"]
    _run(db_session, session, [
        _call("m1", "c1", "read_artifact_nodes", {"node_ids": [case.id, lock.id]}),
        _call("m2", "c2", "move_artifact_node", {"expected_revision": 2,
            "target_node_id": case.id, "new_parent_id": lock.id}), _final(),
    ], text="把 TC003 移到账号锁定下面", key="s5")
    db_session.expire_all()
    assert db_session.get(ArtifactNode, case.id).parent_id == lock.id


def test_6_duplicate_only_never_changes_revision(world, db_session):
    user, artifact, session = world
    ops = []
    for _ in range(2):
        item = _case("重复登录"); item["parent_id"] = artifact.root_node_id; ops.append(item)
    _apply(db_session, artifact, user, ops)
    before = _revision(db_session, artifact, user)
    gateway = _run(db_session, session, [
        _call("m1", "c1", "find_duplicate_cases", {"threshold": 0.88, "limit": 20,
                                                     "root_node_id": None}), _final(),
    ], text="只查重复，不要修改", key="s6")
    assert _revision(db_session, artifact, user) == before
    assert [block.name for request in gateway.requests for message in request.messages
            if isinstance(message, AssistantMessage) for block in message.content
            if isinstance(block, ToolCall)] == ["find_duplicate_cases"]


def test_7_coverage_diagnoses_then_user_approved_adds_gaps(world, db_session):
    user, artifact, session = world
    before = _revision(db_session, artifact, user)
    _run(db_session, session, [
        _call("m1", "c1", "analyze_test_coverage", {"root_node_id": None}), _final(),
    ], text="检查覆盖情况", key="s7a")
    assert _revision(db_session, artifact, user) == before
    operations = []
    for title, tag in (("边界用例", "边界"), ("异常用例", "异常")):
        content = _case(title, [tag])["content"]
        operations.append({"operation_type": "add_node", "parent_id": artifact.root_node_id,
                           "node": {"node_type": "test_case", "title": title, "content": content}})
    _run(db_session, session, [
        _call("m2", "c2", "batch_apply_artifact_operations",
              {"expected_revision": before, "operations": operations}), _final("f2"),
    ], text="把边界和异常两个缺口补上", key="s7b")
    assert _revision(db_session, artifact, user) == before + 1


def test_8_direct_cases_do_not_force_test_points(world, db_session):
    user, artifact, session = world
    operations = []
    for index in range(3):
        content = _case("x", ["异常"])["content"]
        operations.append({"operation_type": "add_node", "parent_id": artifact.root_node_id,
                           "node": {"node_type": "test_case", "title": f"支付失败 {index+1}",
                                    "content": content}})
    _run(db_session, session, [
        _call("m1", "c1", "batch_apply_artifact_operations",
              {"expected_revision": 1, "operations": operations}), _final(),
    ], text="直接补三条异常用例，不用先建测试点", key="s8")
    nodes = _nodes(db_session, artifact.id)
    assert len([node for node in nodes if node.node_type == "test_case"]) == 3
    modules = [node for node in nodes if node.node_type == "module"]
    assert len(modules) == 1 and modules[0].title == "默认模块"


def test_final_acceptance_story_revisions_1_through_5(world, db_session):
    user, artifact, session = world
    _run(db_session, session, [
        _call("a1", "a1", "get_current_artifact", {}),
        _call("a2", "a2", "batch_apply_artifact_operations", {"expected_revision": 1,
            "operations": [
                {"operation_type": "add_node", "parent_id": artifact.root_node_id,
                 "node": {"node_type": "module", "title": "正常登录"}},
                {"operation_type": "add_node", "parent_id": artifact.root_node_id,
                 "node": {"node_type": "module", "title": "账号锁定"}},
            ]}), _final("af")], text="先列登录测试点", key="story1")
    assert _revision(db_session, artifact, user) == 2
    lock = db_session.query(ArtifactNode).filter(ArtifactNode.title == "账号锁定").one()
    adds = []
    for title in ("TC021", "TC022", "TC023"):
        adds.append({"operation_type": "add_node", "parent_id": lock.id,
                     "node": {"node_type": "test_case", "title": title,
                              "content": _case(title, ["边界"])["content"]}})
    _run(db_session, session, [
        _call("b1", "b1", "read_artifact_nodes", {"node_ids": [lock.id]}),
        _call("b2", "b2", "batch_apply_artifact_operations",
              {"expected_revision": 2, "operations": adds}), _final("bf")],
        text="锁定补三个边界", key="story2")
    assert _revision(db_session, artifact, user) == 3
    cases = db_session.query(ArtifactNode).filter(
        ArtifactNode.artifact_id == artifact.id, ArtifactNode.node_type == "test_case",
        ArtifactNode.deleted_revision.is_(None)).order_by(ArtifactNode.id).all()
    _run(db_session, session, [
        _call("c1", "c1", "get_artifact_diff", {"revision_count": 1}),
        _call("c2", "c2", "delete_artifact_node", {"expected_revision": 3,
                                                     "target_node_id": cases[1].id}), _final("cf")],
        text="第二个不要", key="story3")
    assert _revision(db_session, artifact, user) == 4
    _run(db_session, session, [
        _call("d1", "d1", "read_artifact_nodes", {"node_ids": [cases[0].id]}),
        _call("d2", "d2", "update_artifact_node", {"expected_revision": 4,
            "target_node_id": cases[0].id, "patch": {"content": {
                "preconditions": [], "steps": [{"action": "等待30分钟", "data": None}],
                "expected_results": ["允许重新登录"], "priority": "P1", "tags": ["边界"]}}}),
        _final("df")], text="把 TC021 预期改一下", key="story4")
    assert _revision(db_session, artifact, user) == 5
    _run(db_session, session, [
        _call("e1", "e1", "find_duplicate_cases", {"root_node_id": None,
                                                     "threshold": 0.88, "limit": 20}), _final("ef")],
        text="只检查重复，不修改", key="story5")
    _run(db_session, session, [
        _call("f1", "f1", "analyze_test_coverage", {"root_node_id": None}), _final("ff")],
        text="检查覆盖率", key="story6")
    assert _revision(db_session, artifact, user) == 5
    visible = {node.title for node in _nodes(db_session, artifact.id)}
    assert "TC022" not in visible and {"TC021", "TC023"} <= visible


def test_revision_conflict_returns_to_model_then_rereads_and_recovers(world, db_session):
    user, artifact, session = world
    item = _case("TC003"); item["parent_id"] = artifact.root_node_id
    _apply(db_session, artifact, user, [item])  # manual/current revision is now 2
    target = db_session.query(ArtifactNode).filter(ArtifactNode.title == "TC003").one()
    gateway = _run(db_session, session, [
        _call("r1", "r1", "update_artifact_node", {"expected_revision": 1,
            "target_node_id": target.id, "patch": {"title": "stale write"}}),
        _call("r2", "r2", "read_artifact_nodes", {"node_ids": [target.id]}),
        _call("r3", "r3", "update_artifact_node", {"expected_revision": 2,
            "target_node_id": target.id, "patch": {"title": "recovered write"}}),
        _final("rf"),
    ], text="修改 TC003", key="conflict")
    db_session.expire_all()
    assert db_session.get(ArtifactNode, target.id).title == "recovered write"
    assert _revision(db_session, artifact, user) == 3
    tool_results = [message for request in gateway.requests for message in request.messages
                    if getattr(message, "role", None) == "toolResult"]
    assert any(message.is_error and message.details.get("error_code") == "revision_conflict"
               for message in tool_results)


def test_workspace_here_reads_selected_module_before_any_write(world, db_session):
    user, artifact, session = world
    _apply(db_session, artifact, user, [{"operation_type": "add_node",
        "parent_id": artifact.root_node_id, "node_type": "module", "title": "账号锁定"}])
    module = db_session.query(ArtifactNode).filter(ArtifactNode.title == "账号锁定").one()
    gateway = _run(db_session, session, [
        _call("w1", "w1", "read_artifact_nodes", {"node_ids": [module.id]}), _final("wf"),
    ], text="这里有哪些用例？", key="workspace-here", workspace_context={
        "selected_module_id": module.id, "selected_case_id": None, "current_view": "mindmap"})
    assert f"selected module node id: {module.id}" in gateway.requests[0].system_prompt
    assert gateway.requests[1].messages[-1].tool_name == "read_artifact_nodes"


def test_ambiguous_scope_reads_outline_and_asks_without_writing(world, db_session):
    user, artifact, session = world
    _apply(db_session, artifact, user, [
        {"operation_type": "add_node", "parent_id": artifact.root_node_id,
         "node_type": "module", "title": "登录"},
        {"operation_type": "add_node", "parent_id": artifact.root_node_id,
         "node_type": "module", "title": "支付"},
    ])
    before = _revision(db_session, artifact, user)
    gateway = _run(db_session, session, [
        _call("a1", "a1", "read_artifact_outline", {"root_node_id": None,
                                                     "max_depth": 3, "max_nodes": 20}),
        _final("af", "当前有登录和支付模块，你想完善哪部分？"),
    ], text="帮我完善一下测试", key="workspace-ambiguous", workspace_context={
        "selected_module_id": None, "selected_case_id": None, "current_view": "list"})
    assert _revision(db_session, artifact, user) == before
    tool_names = [block.name for request in gateway.requests for message in request.messages
                  if isinstance(message, AssistantMessage) for block in message.content
                  if isinstance(block, ToolCall)]
    assert tool_names == ["read_artifact_outline"]


def test_explicit_unique_module_reads_and_works_without_forced_question(world, db_session):
    user, artifact, session = world
    _apply(db_session, artifact, user, [{"operation_type": "add_node",
        "parent_id": artifact.root_node_id, "node_type": "module", "title": "登录"}])
    module = db_session.query(ArtifactNode).filter(ArtifactNode.title == "登录").one()
    before = _revision(db_session, artifact, user)
    _run(db_session, session, [
        _call("e1", "e1", "read_artifact_nodes", {"node_ids": [module.id]}),
        _call("e2", "e2", "add_artifact_node", {"expected_revision": before,
            "parent_id": module.id, "node": {"node_type": "test_case", "title": "登录边界"}}),
        _final("ef", "已在登录模块补充边界用例。"),
    ], text="给登录模块补边界", key="workspace-explicit", workspace_context={
        "selected_module_id": None, "selected_case_id": None, "current_view": "list"})
    assert _revision(db_session, artifact, user) == before + 1
