from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from pydantic import BaseModel
import httpx



OLLAMA_MODEL = "qwen3.5:4b"
OLLAMA_URL = "http://localhost:11434"

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

"""
{
"model":"qwen3.5:4b",
"created_at":"2026-06-27T02:39:52.921719Z",
"message":{
    "role":"assistant",
    "content":"Hello! How can I help you today?"
},
"done":true,
"done_reason":"stop",
"total_duration":843278833,
"load_duration":139553041,
"prompt_eval_count":17,
"prompt_eval_duration":214781833,
"eval_count":10,
"eval_duration":481586749
}
"""

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
    
    payload = body.model_dump()


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
