"""Negative control: provider Fake tests do not need an outbound socket."""
import asyncio
import json
import socket

import httpx
import pytest

from app.agents.providers.openai_stream_adapter import OpenAIStreamAdapter
from app.agents.providers.streaming import ProviderSnapshot, StreamContext, StreamControl, StreamRequest
from tests_streaming_kit import make_user


def test_fake_transport_works_while_all_connect_entrypoints_are_denied():
    async def go():
        original_connect = socket.socket.connect
        original_connect_ex = socket.socket.connect_ex
        original_create = socket.create_connection
        attempts = []
        def deny(*args, **kwargs):
            attempts.append("denied")
            raise RuntimeError("network denied")
        socket.socket.connect = deny
        socket.socket.connect_ex = deny
        socket.create_connection = deny
        try:
            with pytest.raises(RuntimeError):
                socket.create_connection(("example.invalid", 443))
            probe = socket.socket()
            try:
                with pytest.raises(RuntimeError): probe.connect(("127.0.0.1", 9))
                with pytest.raises(RuntimeError): probe.connect_ex(("127.0.0.1", 9))
            finally:
                probe.close()

            body = ("data: " + json.dumps({"choices": [{"delta": {"content": "ok"},
                    "finish_reason": "stop"}]}) + "\n\ndata: [DONE]\n\n").encode()
            async def handler(request): return httpx.Response(200, content=body, request=request)
            adapter = OpenAIStreamAdapter(async_client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)))
            snapshot = ProviderSnapshot("openai_compatible", "p", "https://fake.invalid", "synthetic", "m", max_tokens=4)
            control = StreamControl(cancel_event=asyncio.Event())
            request = StreamRequest(messages=[make_user()], max_tokens=4)
            events = [event async for event in adapter.stream(snapshot, request, StreamContext("m", 1), control)]
            assert events[-1].type == "done"
            assert len(attempts) == 3
        finally:
            socket.socket.connect = original_connect
            socket.socket.connect_ex = original_connect_ex
            socket.create_connection = original_create
    asyncio.run(go())
