from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from pydantic import BaseModel

from agents import orchestrator
from tools import github

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

class ModelRequest(BaseModel):
    model: str
    messages: list[ModelMessage]
    think: bool


@app.get("/search")
async def search(q: str, sort: str = "stars"):
    return await github.search_repos(q, sort)


@app.post("/message", response_model=MessageResponse)
def receive_message(body: MessageRequest) -> MessageResponse:
    return MessageResponse(result=f"{body.text} received")


@app.post("/generate")
async def generate(body: ModelRequest):
    if not body.model or not body.messages:
        raise HTTPException(status_code=400, detail="No payload provided")

    print("message received", body.messages[-1].content)

    messages = [m.model_dump() for m in body.messages]

    return StreamingResponse(
        orchestrator.run(body.model, messages, body.think),
        media_type="application/x-ndjson",
    )
