"""保存候选 Service：把已审批的候选用例写入业务表（function_cases / api_cases）。

安全规则：
- 数据全部取自 test_case_set Artifact 与 Run/State，不信任前端 payload/project_id；
- 来源重读并比较 source_hash，变化 → agent_source_changed（409），业务表不动；
- 写权限由 Router 层经 permission_service 校验；
- 业务写入 + 审批决议 + Artifact saved + Run succeeded + 事件在同一事务提交，
  异常整体回滚；
- 幂等：审批已 approved 且 candidate_ids 相同 → 返回相同 saved_case_ids
  （resolution_json 持久化，进程重启后仍有效）；不同 candidate_ids → 409。
"""

import json

from sqlalchemy.orm import Session

from app.agents.runtime.errors import AgentApprovalConflictError, AgentError, AgentPermissionError
from app.agents.tools.base import ToolContext
from app.agents.tools.case_context_tools import LoadSourceContextInput, LoadSourceContextTool
from app.models.agent_approval import AgentApproval
from app.models.agent_artifact import AgentArtifact
from app.models.agent_run import AgentRun
from app.models.agent_session import AgentSession
from app.models.api_case import APICase
from app.models.function_case import FunctionCase
from app.services import agent_approval_service, agent_artifact_service, agent_run_service

GATE_SAVE = "save_generated_case_candidates"


def _json_dumps(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def save_candidates(
    db: Session,
    run: AgentRun,
    candidate_ids: list[str],
    requester_user_id: int,
) -> dict:
    session = db.query(AgentSession).filter(AgentSession.id == run.session_id).first()
    if session is None or session.user_id != requester_user_id:
        raise AgentPermissionError(f"用户 {requester_user_id} 无权保存 Run {run.id} 的候选。")

    approval = (
        db.query(AgentApproval)
        .filter(AgentApproval.agent_run_id == run.id, AgentApproval.action_code == GATE_SAVE)
        .first()
    )
    if approval is None:
        raise AgentApprovalConflictError(f"Run {run.id} 没有待处理的保存审批。")

    # 幂等分支必须优先于 run.status 检查：重复保存时 Run 已经是 succeeded
    if approval.status == "approved":
        previous = (approval.resolution_json or {}).get("candidate_ids") or []
        if sorted(previous) == sorted(candidate_ids):
            # 幂等：返回相同 saved_case_ids（resolution_json 持久化，重启后仍有效）
            return {
                "run_id": run.id,
                "saved_count": len((approval.resolution_json or {}).get("saved_case_ids") or []),
                "saved_case_ids": (approval.resolution_json or {}).get("saved_case_ids") or [],
                "candidate_ids": sorted(candidate_ids),
            }
        raise AgentApprovalConflictError("同一审批已用不同 candidate_ids 保存过，不允许重复不同保存。")

    if run.status != "waiting_approval":
        raise AgentError(
            f"Run {run.id} 状态为 {run.status}，只有 waiting_approval 可以保存。",
            error_code="agent_save_not_awaiting",
        )

    if approval.status != "pending":
        raise AgentApprovalConflictError(f"保存审批状态为 {approval.status}，无法保存。")

    if approval.artifact_id is None:
        raise AgentApprovalConflictError("保存审批未关联候选 Artifact。")
    artifact = db.query(AgentArtifact).filter(AgentArtifact.id == approval.artifact_id).first()
    if artifact is None:
        raise AgentApprovalConflictError("保存审批关联的 Artifact 不存在。")
    if artifact.agent_run_id != run.id:
        raise AgentApprovalConflictError("Artifact 与 Run 归属不一致。")

    payload = artifact.payload_json or {}
    candidates = payload.get("candidates") or []
    by_id = {c.get("candidate_id"): c for c in candidates}
    unknown = [cid for cid in candidate_ids if cid not in by_id]
    if unknown:
        raise AgentError(f"候选不存在: {unknown}", error_code="agent_invalid_input")

    # 来源重读并比较 source_hash（409 且业务表不动）
    source_type = payload.get("source_type")
    source_id = payload.get("source_id")
    source_hash = payload.get("source_hash")
    if not source_type or not source_id:
        raise AgentError("Artifact 缺少来源信息", error_code="agent_invalid_input")
    source_out = LoadSourceContextTool().execute(
        ToolContext(user_id=requester_user_id, db=db),
        LoadSourceContextInput(source_type=source_type, source_id=source_id),
    )
    if not source_out.found:
        raise AgentError("来源不存在或已删除", error_code="agent_source_not_found")
    if source_out.source_hash != source_hash:
        raise AgentError(
            "来源内容已变化，保存被拒绝。请重新生成候选用例。",
            error_code="agent_source_changed",
        )

    selected = [by_id[cid] for cid in candidate_ids]
    state = (run.output_json or {}).get("workflow_state") or {}
    module_id = (state.get("source_context") or {}).get("module_id")

    try:
        saved_case_ids: list[int] = []
        if source_type == "requirement":
            for item in selected:
                case = item.get("case") or {}
                row = FunctionCase(
                    project_id=run.project_id,
                    module_id=module_id,
                    requirement_id=source_id,
                    case_code=case.get("case_code") or None,
                    case_name=case.get("case_name") or "未命名用例",
                    case_type=case.get("case_type") or "其他",
                    source="llm",
                    priority=case.get("priority") or "P1",
                    precondition=case.get("precondition") or None,
                    steps_json=case.get("steps_json") or None,
                    test_data_json=case.get("test_data_json") or None,
                    expected_result=case.get("expected_result") or None,
                    status="active",
                    remark=case.get("remark") or None,
                )
                db.add(row)
                db.flush()
                saved_case_ids.append(row.id)
        else:
            for item in selected:
                case = item.get("case") or {}
                row = APICase(
                    name=case.get("name") or "未命名用例",
                    description=case.get("description") or "",
                    method=str(case.get("method") or "GET").upper(),
                    url=case.get("url") or "",
                    headers=_json_dumps(case.get("headers")) if case.get("headers") else None,
                    body=_json_dumps(case.get("body")),
                    expected_result=_json_dumps(case.get("expected_result")),
                    project_id=run.project_id,
                    module_id=module_id,
                    case_type=case.get("case_type") or "其他",
                    source="llm",
                    priority=case.get("priority") or "P1",
                    status="active",
                )
                db.add(row)
                db.flush()
                saved_case_ids.append(row.id)

        # 同事务：Artifact saved + Approval approved + Run succeeded + 事件一次
        agent_artifact_service.update_status(db, artifact, "saved")
        agent_approval_service.approve(
            db, approval,
            resolved_by_user_id=requester_user_id,
            resolution_json={
                "candidate_ids": sorted(candidate_ids),
                "saved_case_ids": saved_case_ids,
            },
        )
        agent_run_service.transition_status(db, run, "succeeded")
        agent_run_service.mark_finished_at(db, run)
        agent_run_service.append_event(
            db, run.session_id, run.id, "cases_saved",
            {"saved_count": len(saved_case_ids)},
        )
        db.commit()
    except Exception:
        db.rollback()  # 任一步异常整体回滚，不残留部分写入
        raise

    return {
        "run_id": run.id,
        "saved_count": len(saved_case_ids),
        "saved_case_ids": saved_case_ids,
        "candidate_ids": sorted(candidate_ids),
    }
