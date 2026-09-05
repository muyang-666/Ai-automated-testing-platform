"""P06 Conversation 执行事件持久化（Worker 侧，SSE 的 DB Source of Truth）。

原则（05 §15 / P06 §10-§11）：
- 不逐 token 落库；文本增量按时间/大小聚合为粗粒度行（非 transient-only，
  因为 Worker 与 API 是独立进程，DB 是唯一可恢复的跨进程通道）；
- 持久化安全可展示事件：tool_execution_start/end、conversation_text_delta
  （聚合）；message_committed 与消息由 Runner 原子提交，run 生命周期也由 Runner 写；
- 绝不落库隐藏 reasoning / 原始敏感日志（tool end 只带名称/error_code/is_error）。
"""
import time
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.services.agent import agent_run_service

TEXT_DELTA_LIMIT_CHARS = 400
TEXT_DELTA_INTERVAL_SECONDS = 0.25


class ConversationEventPersister:
    def __init__(self, session_factory: Callable[[], Session], *,
                 session_id: int, run_id: int, interval_seconds: float = TEXT_DELTA_INTERVAL_SECONDS,
                 delta_limit_chars: int = TEXT_DELTA_LIMIT_CHARS, now_provider=None,
                 worker_id: str | None = None, execution_token: int | None = None):
        self._session_factory = session_factory
        self.session_id = session_id
        self.run_id = run_id
        self.interval_seconds = interval_seconds
        self.delta_limit_chars = delta_limit_chars
        self._now = now_provider or time.monotonic
        self._text_buffer: list[str] = []
        self._last_flush = self._now()
        self._message_id: str | None = None
        self.worker_id = worker_id
        self.execution_token = execution_token

    # ── Runner event_sink 入口（同步） ──
    def __call__(self, event: Any) -> None:
        event_type = getattr(event, "type", "")
        try:
            if event_type == "message_update":
                inner = getattr(event, "assistant_message_event", None)
                if inner is not None and getattr(inner, "type", "") == "text_delta":
                    self._message_id = getattr(getattr(event, "message", None),
                                               "message_id", self._message_id)
                    self._text_buffer.append(getattr(inner, "delta", ""))
                    if (len("".join(self._text_buffer)) >= self.delta_limit_chars
                            or self._now() - self._last_flush >= self.interval_seconds):
                        self.flush()
            elif event_type == "message_end":
                # message_end is an in-memory loop lifecycle event, not a DB
                # commit.  Flush streaming text here; ConversationRunner writes
                # conversation_message_committed atomically with AgentMessage.
                self.flush()
            elif event_type == "tool_execution_start":
                self.flush()
                self._append("conversation_tool_started", {
                    "tool_call_id": getattr(event, "tool_call_id", None),
                    "tool_name": getattr(event, "tool_name", None),
                })
            elif event_type == "tool_execution_end":
                self.flush()
                result = getattr(event, "result", None) or {}
                details = result.get("details") if isinstance(result, dict) else None
                error_code = None
                if isinstance(details, dict):
                    error_code = details.get("error_code")
                self._append("conversation_tool_finished", {
                    "tool_call_id": getattr(event, "tool_call_id", None),
                    "tool_name": getattr(event, "tool_name", None),
                    "is_error": bool(getattr(event, "is_error", False)),
                    "error_code": error_code,  # 不落原始日志/敏感内容
                })
        except Exception:
            # 事件持久化是 best-effort 通道；失败不阻断 Agent 主执行。
            return

    # ── 收尾 flush（run 结束后由 Worker 调用一次） ──
    def flush(self) -> None:
        text = "".join(self._text_buffer)
        if not text:
            self._last_flush = self._now()
            return
        payload = {"message_id": self._message_id, "text": text}
        self._text_buffer = []
        self._last_flush = self._now()
        self._append("conversation_text_delta", payload)

    def _append(self, event_type: str, payload: dict) -> None:
        session = self._session_factory()
        try:
            if self.worker_id is not None and self.execution_token is not None:
                agent_run_service.assert_execution_ownership(
                    session, self.run_id, self.worker_id, self.execution_token,
                )
            agent_run_service.append_event(session, self.session_id, self.run_id,
                                           event_type, payload)
            session.commit()
        finally:
            session.close()
