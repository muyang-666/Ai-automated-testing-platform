"""P10.1-B3 ConversationSummarizer abstraction + 固定 Prompt（不绑定某家 SDK）。"""

from dataclasses import dataclass, field
from typing import Any

from app.agents.conversation.context_builder import estimate_text_tokens

SUMMARY_PROMPT = """You are writing a concise incremental conversation summary in Chinese.

Use the existing summary (if any) together with the new messages below.
Keep only:
- the user's current goal
- confirmed constraints
- important completed actions
- relevant module/case/artifact references
- unresolved items
- referents needed later ("第一个/第二个/这个模块")
- recent meaningful revisions

Drop greetings, streaming deltas, large raw Tool JSON, debug output.
Do not invent information. Artifact state may have changed.
This summary is historical context, not current Artifact authority.

Existing summary (through {existing_through}):
{existing_summary}

New messages (sequence {first_seq}..{last_seq}):
{message_text}

Return only the short stable summary text, no markdown report."""


@dataclass
class SummaryCallRecord:
    existing_summary: str | None = None
    received_message_ids: list[str] = field(default_factory=list)
    target_through_sequence: int | None = None
    provider: str | None = None
    model: str | None = None
    usage: dict[str, Any] | None = None
    estimated_tokens: int | None = None


class ConversationSummarizer:
    """async summarize(existing, messages, target, budget, runtime) -> SummaryResult。"""

    async def summarize(self, *, existing_summary, messages, target_through_sequence,
                        summary_token_budget, runtime_context=None):
        raise NotImplementedError


def build_summary_user_text(messages) -> str:
    parts = []
    for message in messages:
        body = getattr(message, "content", "")
        if isinstance(body, list):
            body = " ".join(str(getattr(b, "text", "")) for b in body)
        parts.append(f"- {getattr(message, 'role', '?')}: {body}")
    return "\n".join(parts[:400])


def estimate_summary_tokens(text: str) -> int:
    return estimate_text_tokens(text)
