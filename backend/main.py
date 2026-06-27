from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from pydantic import BaseModel
import httpx
import json



OLLAMA_MODEL = "qwen3.5:4b"
OLLAMA_URL = "http://localhost:11434"

SYSTEM_PROMPT = """You are a helpful assistant. Be concise and direct.

You have access to agents that can fetch real data when you need it:
- github_agent: use when the user asks about a specific repository, file, or code on GitHub

If you can answer from your own knowledge, do so. Only call an agent when you actually need live data you don't have.

When you need to call an agent, respond with JSON only, nothing else:
{"agent": "github_agent", "query": "<what you need from it>"}"""

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class MessageRequest(BaseModel):
    text: str


class MessageResponse(BaseModel):
    result: str

class ModelMessage(BaseModel):
    role: str
    content: str

class ModelResponse(BaseModel):
    model: str
    created_at: str
    message: ModelMessage
    done: bool
    done_reason: str
    total_duration: int
    load_duration: int
    prompt_eval_count: int

class ModelRequest(BaseModel):
    model: str
    messages: list[ModelMessage]
    stream: bool
    think: bool

@app.post("/message", response_model=MessageResponse)
def receive_message(body: MessageRequest) -> MessageResponse:
    return MessageResponse(result=f"{body.text} received")


@app.post("/generate")
async def generate(body: ModelRequest):
    if not body.model or not body.messages:
        raise HTTPException(status_code=400, detail="No payload provided")
    
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        *[m.model_dump() for m in body.messages],
    ]

    # blocking call to check if the model wants to route to an agent
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{OLLAMA_URL}/api/chat",
            json={"model": body.model, "messages": messages, "stream": False},
        )
        resp.raise_for_status()
        content = resp.json()["message"]["content"]

    try:
        routing = json.loads(content)
        if "agent" in routing:
            print(f"[agent call] agent={routing['agent']} query={routing.get('query')}")
            # agent execution goes here
            return
    except (json.JSONDecodeError, KeyError):
        pass

    # not an agent call — stream normally
    payload = {
        "model": body.model,
        "messages": messages,
        "stream": True,
        "think": body.think,
    }

    async def proxy_stream():
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{OLLAMA_URL}/api/chat",
                json=payload
            ) as resp:
                resp.raise_for_status()
                async for chunk in resp.aiter_lines():
                    if chunk:
                        yield chunk + "\n"

    return StreamingResponse(proxy_stream(), media_type="application/x-ndjson")
