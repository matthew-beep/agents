import httpx
import json

from agents import github_agent, ollama, events
OLLAMA_URL = "http://localhost:11434"

SYSTEM_PROMPT = """You are a helpful assistant. Be concise and direct.

You have access to specialized agents that can fetch real data:
- github_agent: use when the user asks about a GitHub repository, file, or code

If you can answer from your own knowledge, do so. Only call an agent when you need live data."""

PLANNER_SYSTEM_PROMPT = """
You are a routing assistant. Respond with JSON only.

Decide how the user's message should be handled:

- If you can answer from your own knowledge: {"mode": "direct"}
- If you need live data from an agent:       {"mode": "agentic", "plan": "..."}

Available agents:
- github_agent: fetches live data from GitHub — repos, file trees, file contents, READMEs

The "plan" value is one sentence, first-person, describing what you're about to do.
Example: {"mode": "agentic", "plan": "I'll inspect the repository and trace the auth flow."}

Return nothing except the JSON object.

"""


"""
Good order to tackle this in, bottom-up so each piece is independently testable before you wire it to the next:

1. events.py first. Smallest, no dependencies — add thinking_event() and agent_error_event(), delete PlanEvent/plan_event(). Five minutes, and every other file leans on it.

2. base.py's run_agent() next — this is the active bug, and it's the most isolated thing to fix. It doesn't touch the orchestrator or frontend at all, so you can test it completely standalone: write a throwaway script that calls run_agent() directly with a real GitHub query and just prints whatever it yields. Verify by eye:
- every Ollama call it makes has stream: false whenever tools is attached (no exceptions)
- tool_call events show up live, one per tool, as they fire — not bunched at the end
- it terminates via agent_result
- force a bad query (nonexistent repo) and confirm agent_error fires and it doesn't crash
- temporarily set AGENT_MAX_ROUNDS = 1 and confirm it actually cuts off a multi-tool query

Don't move on until this works in isolation — it's the piece most likely to have subtle bugs (the inner loop, the round cap, the error path), and it's much easier to debug with print() on a script than through a live stream.

3. orchestrator.py's run() loop. Delete the dead docstring block and PLANNER_SYSTEM_PROMPT, write the real loop calling the now-working run_agent(). Test with curl straight against /generate (like we did earlier in this session) and read the raw NDJSON — you want to see, in order: thinking once, then agent_start/tool_call/agent_end for round 1, tool results appended, round 2 firing correctly for a query that needs two lookups, then token/done. This is still backend-only — no frontend needed to verify it.

4. Frontend last. Once you can see the correct event sequence over curl, page.tsx becomes mechanical: add the phase state machine, handle agent_error, delete plan state and the PlanEvent type. You're just rendering an event stream you've already proven correct.

Want to start on #2 now, or #1 to get it out of the way first? I can review as you go rather than write it — happy to look at diffs, run your curl tests, or poke at edge cases you might've missed.


"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "github_agent",
            "description": "Fetch data from GitHub — repos, file trees, file contents, READMEs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What you need from GitHub"}
                },
                "required": ["query"],
            },
        },
    }
]

# Maps agent tool names to their run functions.
AGENT_MAP = {
    "github_agent": github_agent.run,
}


async def run(model: str, messages: list[dict], think: bool):
    #planner_messages = [{"role": "system", "content": PLANNER_SYSTEM_PROMPT}, *messages]
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, *messages]

    """
    need to implement our own streaming responses here
    """
    
    call_rounds = 0
    MAX_ROUNDS = 5


    """
    while true:

        resp = await ollama.chat(client, model, messages, think=False, tools=TOOLS)

        if resp.get("tool_calls"):

            # execute agent loop
    
        call_rounds += 1

        if call_rounds < MAX_ROUNDS:


    """
    # while True:
    tool_calls = []

    async with httpx.AsyncClient(timeout=300.0) as client:
        yield events.emit(events.plan_event("Thinking..."))
        plan = await ollama.chat(client, model, messages, think=False, tools=TOOLS)
        print("plan", plan)
        async for line in ollama.emit_token_stream(client, model, messages, think=False):
            yield line
        
"""
        if plan["mode"] == "agentic":
            async for token in ollama.emit_token_stream(client, model, messages, think=False):
                yield events.emit(token)
                print("token", token)

        
        async with client.stream(
            "POST",
            f"{OLLAMA_URL}/api/chat",
            json={"model": model, "messages": messages, "tools": TOOLS, "stream": True, "think": think},
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line:
                    continue
                chunk = json.loads(line)
                msg = chunk.get("message", {})

                if msg.get("tool_calls"):
                    tool_calls.extend(msg["tool_calls"])
                    # Content may have already reached the frontend — tell it to discard.
                    yield json.dumps({"type": "reset"}) + "\n"
                else:
                    # Yield live while the stream is open.
                    print("yielding line", line)
                    yield line + "\n"

    # Content was already streamed live — nothing left to do on the final pass.
    if not tool_calls:
        print("no tool calls, breaking")
        break

    # For each agent call: emit start event, run the agent (fire-and-collect),
    # emit end event with its tool history, then feed its response back to Ollama.
    messages.append({"role": "assistant", "tool_calls": tool_calls})
    for tc in tool_calls:
        fn_name = tc["function"]["name"]
        fn_args = tc["function"]["arguments"]

        yield json.dumps({"type": "agent_start", "agent": fn_name}) + "\n"

        agent_fn = AGENT_MAP.get(fn_name)
        if agent_fn:
            content, tool_history = await agent_fn(
                model, [{"role": "user", "content": fn_args["query"]}], think
            )
        else:
            content, tool_history = f"unknown agent: {fn_name}", []

        yield json.dumps({"type": "agent_end", "agent": fn_name, "tools": tool_history}) + "\n"

        messages.append({"role": "tool", "content": content})



        
        """