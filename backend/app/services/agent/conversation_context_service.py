"""P10.1-B3 ConversationContextPreparer：Runner 与 SummaryOrchestrator 之间的 DB 适配层。

Runner 只调用本模块（prepare_context），不拼 prompt、不直接调 Provider、
不自己处理摘要。数据链（spec #10）：

    Run user sequence = N
      → 读 bounded history（owner ≤ N，SQL 侧过滤，逻辑序 rank 1..N）
      → 读 latest summary
      → build_prepared_context()（probe：装得下 → 0 次 Summarizer）
      → 需要压缩 → select_incremental_inputs()
      → 结束 DB 读事务（rollback，不跨模型调用持事务）
      → Summarizer（模型调用，无 DB 事务）
      → 短 DB write transaction（create/conditional update + commit）
      → winning 重读（冲突时采用 DB 已有值，不覆盖、不重跑模型）
      → 重建 PreparedContext
      → Runner 只消费最终 PreparedContext

事务边界约定：本模块调用方（Runner）在调用 prepare 前已完成自身读事务释放；
DbSummaryIO 每次 get/write 自开短事务并立即 commit/rollback，绝不持有
Session 事务跨模型调用。本模块不修改/删除任何历史 Message 行。
"""

from dataclasses import dataclass, field
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.agents.conversation.context_builder import ContextBudgetConfig, PreparedContext
from app.agents.conversation.messages import Message, parse_message
from app.agents.conversation.summary_orchestrator import (
    OrchestrationResult,
    SummaryIO,
    SummaryOrchestrator,
    SummaryStoreView,
)
from app.agents.conversation.summarizer import ConversationSummarizer
from app.agents.runtime.errors import AgentError
from app.models.agent.agent_message import AgentMessage
from app.models.agent.agent_run import AgentRun
from app.services.agent import conversation_repository, conversation_summary_service


class ConversationContextLimitError(AgentError):
    """最终无法构造合法 context（预算内）：Runner 映射 Run=context_limit。"""

    error_code = "context_limit"

    def __init__(self, *, reason: str, estimated_input_tokens: int,
                 max_input_tokens: int):
        self.reason = reason
        self.estimated_input_tokens = int(estimated_input_tokens)
        self.max_input_tokens = int(max_input_tokens)
        super().__init__(
            f"对话上下文无法在预算内构造（{reason}）", error_code="context_limit")

    def event_payload(self) -> dict[str, Any]:
        return {
            "reason": self.reason,
            "estimated_input_tokens": self.estimated_input_tokens,
            "max_input_tokens": self.max_input_tokens,
        }


class DbSummaryIO(SummaryIO):
    """DB 版 SummaryIO：每次调用独立短事务（读后 rollback / 写后 commit）。

    契约：调用方不得在两次调用之间让 Session 持有 pending 写状态。
    """

    def __init__(self, db: Session, conversation_id: int):
        self._db = db
        self._conversation_id = conversation_id

    def get_current(self) -> SummaryStoreView:
        view = SummaryStoreView()
        try:
            row = conversation_summary_service.get_latest_summary(
                self._db, self._conversation_id)
            if row is not None:
                view.through_visible_rank = row.through_visible_rank
                view.through_message_id = row.through_message_id
                view.summary_text = row.summary_text
        finally:
            self._db.rollback()  # 立即释放读事务
        return view

    def write_incremental(self, *, expected_through_visible_rank, new_through_visible_rank,
                          new_through_message_id, summary_text, source_message_count,
                          provider=None, model=None) -> bool:
        """审计 #3 结论：ConversationSummary 是 monotonic derived cache——
        只允许 through 单调向前（条件更新 + SAVEPOINT 唯一性），写者即使已失去
        execution ownership 也只会写下真实历史 prefix 的摘要、绝不会覆盖更新的
        winning 值，因此 Summary write 本身不需要 execution_token fencing；
        Run 生命周期事件（context_prepared/compacted/limit 等）仍须 fencing。
        """
        if expected_through_visible_rank <= 0:
            row = conversation_summary_service.create_summary(
                self._db, conversation_id=self._conversation_id,
                through_visible_rank=new_through_visible_rank,
                through_message_id=new_through_message_id,
                summary_text=summary_text,
                source_message_count=source_message_count,
                provider=provider, model=model)
            created = row.through_visible_rank == new_through_visible_rank
            self._db.commit()  # 短写事务立即结束
            return created
        updated = conversation_summary_service.conditional_update_summary(
            self._db, conversation_id=self._conversation_id,
            expected_through_visible_rank=expected_through_visible_rank,
            new_through_visible_rank=new_through_visible_rank,
            new_through_message_id=new_through_message_id,
            summary_text=summary_text, source_message_count=source_message_count,
            provider=provider, model=model)
        if updated:
            self._db.commit()
        else:
            self._db.rollback()  # 被更晚 Summary 抢先：不留脏事务
        return updated


@dataclass
class PreparedRunContext:
    prepared: PreparedContext
    until_sequence_no: int
    current_user_message_id: str
    full_message_count: int
    compaction_model_calls: int
    summary_refreshed: bool
    summary_refresh_failed: bool
    context_limit_reason: str | None
    diagnostics: dict[str, Any] = field(default_factory=dict)


def build_artifact_runtime_section(db: Session, *, requester_user_id: int,
                                   artifact_id: int | None,
                                   workspace_context: dict | None = None) -> str | None:
    """P10.1-B3 spec #27/#28：runtime metadata section（artifact id/title/current
    revision/selected module/case/view），revision 必须实时（prep 时刻）。

    可见性沿用 P09.3B §2.2：project-scoped Artifact 需当前用户 Project read
    ACL；不可见/无权限一律按不可用处理（不泄漏）。绝不读取 Node 内容/Diff
    （P10.1-C 范畴）。工具仍是 Artifact 当前状态的唯一权威。
    """
    if artifact_id is None:
        return None
    from app.models.test_artifact.test_artifact import TestArtifact
    from app.models.user import User
    from app.services.permission_service import can_read_project

    owner = db.get(User, requester_user_id)
    row = db.get(TestArtifact, artifact_id)
    if row is None:
        return None
    if row.project_id is not None and (owner is None
                                       or not can_read_project(db, owner, row.project_id)):
        return None
    workspace = workspace_context or {}
    module_id = workspace.get("selected_module_id")
    case_id = workspace.get("selected_case_id")
    view = workspace.get("current_view")
    lines = [
        "[Current Artifact runtime metadata (at context preparation time)]",
        f"- artifact id: {row.id}",
        f"- artifact title: {row.title}",
        f"- artifact current revision: {row.current_revision}",
        f"- selected module id: {module_id if module_id is not None else 'none'}",
        f"- selected test case id: {case_id if case_id is not None else 'none'}",
        f"- current view: {view if view is not None else 'none'}",
        "Artifact facts referenced in the history summary may be stale; "
        "always read current Artifact state with tools before acting.",
    ]
    return "\n".join(lines)


class ConversationContextPreparer:
    def __init__(self, *, summarizer: ConversationSummarizer,
                 budget: ContextBudgetConfig | None = None,
                 artifact_section_builder: Callable = build_artifact_runtime_section):
        self.summarizer = summarizer
        self.budget = budget or ContextBudgetConfig()
        self._artifact_section_builder = artifact_section_builder

    async def prepare(
        self,
        db: Session,
        run: AgentRun,
        *,
        requester_user_id: int,
        system_sections: list[str] | None = None,
        cancel_event: Any | None = None,
        deadline: float | None = None,
    ) -> PreparedRunContext:
        """为一个已 running 的 conversation Run 准备上下文（读→压缩→写→重建）。

        cancel_event/deadline：转发给 Summarizer（审计 #3），取消时快速失败。
        抛 ConversationContextLimitError = 最终无法构造合法 context；
        其它异常（数据损坏等）由 Runner 统一失败路径处理。
        """
        conversation_id = run.session_id
        if run.user_message_id is None:
            raise AgentError("conversation Run 缺少首条用户消息关联",
                             error_code="agent_run_data_invalid")
        user_row = db.get(AgentMessage, run.user_message_id)
        if user_row is None or user_row.session_id != conversation_id or user_row.role != "user":
            raise AgentError("首条用户消息记录缺失", error_code="agent_run_data_invalid")
        if not user_row.message_id:
            raise AgentError("首条用户消息缺少稳定 message_id",
                             error_code="agent_run_data_invalid")
        until = int(user_row.sequence_no)
        current_user_message_id = user_row.message_id

        # 1) SQL 侧 owner 边界读取 + 逻辑序（含后续 follow-up 可见性边界，spec #16-#18）
        rows = conversation_repository.list_run_visible_message_rows(
            db, conversation_id, until)
        pairs: list[tuple[int, Message]] = []
        for rank, row in enumerate(rows, start=1):
            if not isinstance(row.content_json, dict):
                raise AgentError("会话消息缺少版本化内容",
                                 error_code="agent_run_data_invalid")
            try:
                message = parse_message(row.content_json)
            except Exception:
                raise AgentError("会话消息合同无效", error_code="agent_run_data_invalid") from None
            if row.message_id != message.message_id \
                    or row.schema_version != message.schema_version:
                raise AgentError("会话消息标识或版本不一致",
                                 error_code="agent_run_data_invalid")
            pairs.append((rank, message))
        if not pairs or pairs[-1][1].message_id != current_user_message_id:
            raise AgentError("恢复的历史未以当前 Turn 用户消息结尾",
                             error_code="agent_run_data_invalid")

        # 2) Artifact runtime metadata（同一读事务内取实时 revision，spec #27/#28）
        from app.services.agent.conversation_service import (
            artifact_context_from_run,
            workspace_context_from_run,
        )
        sections = list(system_sections or [])
        artifact_id = artifact_context_from_run(run).get("artifact_id")
        workspace_context = workspace_context_from_run(run)
        metadata_section = self._artifact_section_builder(
            db, requester_user_id=requester_user_id, artifact_id=artifact_id,
            workspace_context=workspace_context)
        if metadata_section:
            sections.append(metadata_section)

        # 2b) invariant 校验（审计 #1）：已有 summary 的 through_message_id 锚点必须
        # 仍是当前可见序中 through_visible_rank 位置的那条消息——未来新 Run/消息
        # 只会追加在已覆盖 prefix 之后，prefix 位置不变；若错位说明数据不一致。
        existing = conversation_summary_service.get_latest_summary(db, conversation_id)
        if existing is not None and existing.through_message_id and \
                0 < existing.through_visible_rank <= len(pairs):
            boundary = pairs[existing.through_visible_rank - 1][1]
            if boundary.message_id != existing.through_message_id:
                raise AgentError(
                    "summary through_message_id 锚点与可见逻辑序不一致",
                    error_code="agent_run_data_invalid")

        # 3) 结束读事务：Summarizer 模型调用期间无任何 DB 事务（spec #10/#32）
        db.rollback()

        # 4) 编排：probe → 需要时一次压缩 → 短写事务 → 重建（spec #9/#11/#25/#26）
        orchestrator = SummaryOrchestrator(self.summarizer, self.budget)
        result: OrchestrationResult = await orchestrator.prepare(
            seq_messages=pairs,
            current_user_message_id=current_user_message_id,
            system_sections=sections,
            io=DbSummaryIO(db, conversation_id),
            cancel_event=cancel_event,
            deadline=deadline,
        )
        prepared = result.prepared
        if prepared.context_limit:
            reason = result.context_limit_reason or prepared.context_limit_reason \
                or "working_context_too_large"
            raise ConversationContextLimitError(
                reason=reason,
                estimated_input_tokens=prepared.estimated_tokens,
                max_input_tokens=self.budget.max_input_tokens,
            )
        return PreparedRunContext(
            prepared=prepared,
            until_sequence_no=until,
            current_user_message_id=current_user_message_id,
            full_message_count=len(pairs),
            compaction_model_calls=result.compaction_model_calls,
            summary_refreshed=result.summary_refreshed,
            summary_refresh_failed=result.summary_refresh_failed,
            context_limit_reason=result.context_limit_reason,
            diagnostics=result.diagnostics,
        )

