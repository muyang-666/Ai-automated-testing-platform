"""One full P02 Gateway -> P03 Loop -> tool -> P02 Gateway Fake HTTP flow."""
import asyncio
import json

import httpx
from pydantic import BaseModel

from app.agents.conversation.loop import AgentLoopConfig, AgentLoopContext, run_agent_loop
from app.agents.conversation.messages import UserMessage
from app.agents.providers.openai_stream_adapter import OpenAIStreamAdapter
from app.agents.providers.streaming import ProviderSnapshot
from app.agents.registry.tool_registry import ToolDefinition, ToolRegistry
from app.services.llm.llm_gateway import LLMGateway


class EchoInput(BaseModel):
    value: str


def sse(*payloads):
    return "".join(f"data: {json.dumps(payload, ensure_ascii=False) if payload != '[DONE]' else payload}\n\n"
                   for payload in payloads).encode()


def test_real_p02_gateway_drives_tool_round_trip_with_fake_http():
    requests = []
    first = sse(
        {"id": "r1", "choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c1",
            "function": {"name": "echo", "arguments": "{\"value\":\"hi\"}"}}]}, "finish_reason": None}]},
        {"choices": [{"delta": {}, "finish_reason": "tool_calls"}]}, "[DONE]",
    )
    second = sse(
        {"id": "r2", "choices": [{"delta": {"content": "结果是 hi"}, "finish_reason": "stop"}]},
        "[DONE]",
    )
    async def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, content=first if len(requests) == 1 else second, request=request)
    stream_adapter = OpenAIStreamAdapter(async_client_factory=lambda: httpx.AsyncClient(
        transport=httpx.MockTransport(handler)))
    gateway = LLMGateway(max_retries=0, stream_adapters={"openai_compatible": stream_adapter})
    registry = ToolRegistry()
    handler_calls = []
    registry.register(ToolDefinition(name="echo", input_model=EchoInput,
        handler=lambda arguments, runtime: handler_calls.append(arguments) or arguments["value"]))
    events = []
    ids = iter(["assistant-1", "tool-result-1", "assistant-2"])
    config = AgentLoopConfig(gateway=gateway,
        snapshot=ProviderSnapshot("openai_compatible", "fake", "https://fake.invalid", "synthetic-key", "m", max_tokens=30),
        event_sink=events.append, cancel_event=asyncio.Event(),
        id_factory=lambda: next(ids), timestamp_factory=lambda: 1)
    context = AgentLoopContext("You are helpful", [], registry)

    result = asyncio.run(run_agent_loop(prompts=[
        UserMessage(message_id="u1", timestamp=1, role="user", content="echo hi")
    ], context=context, config=config))

    assert result.status == "completed" and handler_calls == [{"value": "hi"}]
    assert len(requests) == 2
    assert any(message["role"] == "tool" and message["tool_call_id"] == "c1"
               for message in requests[1]["messages"])
    assert result.new_messages[-1].content[0].text == "结果是 hi"
    assert "message_update" in [event.type for event in events]
    assert [event.type for event in events][-1] == "agent_end"
