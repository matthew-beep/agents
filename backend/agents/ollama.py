import json
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx

from agents.events import done_event, emit, token_event

OLLAMA_URL = "http://localhost:11434"
CHAT_URL = f"{OLLAMA_URL}/api/chat"


def _chat_payload(
    model: str,
    messages: list[dict],
    *,
    think: bool,
    stream: bool,
    tools: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": stream,
        "think": think,
    }
    if tools is not None:
        payload["tools"] = tools
    return payload


async def chat(
    client: httpx.AsyncClient,
    model: str,
    messages: list[dict],
    *,
    think: bool,
    tools: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    resp = await client.post(
        CHAT_URL,
        json=_chat_payload(model, messages, think=think, stream=False, tools=tools),
    )
    resp.raise_for_status()
    return resp.json()


async def emit_token_stream(
    client: httpx.AsyncClient,
    model: str,
    messages: list[dict],
    *,
    think: bool,
    tools: list[dict[str, Any]] | None = None,
) -> AsyncIterator[str]:
    """Consume an Ollama streaming response and yield protocol events."""
    start = time.perf_counter()

    async with client.stream(
        "POST",
        CHAT_URL,
        json=_chat_payload(model, messages, think=think, stream=True, tools=tools),
    ) as resp:
        resp.raise_for_status()
        async for line in resp.aiter_lines():
            if not line:
                continue
            chunk = json.loads(line)
            msg = chunk.get("message", {})

            if content := msg.get("content"):
                yield emit(token_event(content))

            if chunk.get("done"):
                duration_ms = int((time.perf_counter() - start) * 1000)
                eval_count = chunk.get("eval_count") or 0
                eval_duration = chunk.get("eval_duration") or 0
                tokens_per_sec = (
                    eval_count / (eval_duration / 1e9) if eval_duration else None
                )
                yield emit(
                    done_event(
                        tokens=eval_count or None,
                        tokens_per_sec=round(tokens_per_sec, 1) if tokens_per_sec else None,
                        duration_ms=duration_ms,
                    )
                )
