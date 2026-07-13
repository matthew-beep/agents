import httpx
import json
import time
from agents import ollama, events, registry
from agents.base import run_agent
OLLAMA_URL = "http://localhost:11434"

SYSTEM_PROMPT = f"""You are a helpful assistant. Be concise and direct.

You have access to specialized agents that can fetch real data:
{registry.agent_directory()}

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

2. base.py's run_agent() next — this is the active bug, and it's the most isolated thing to fix. 
It doesn't touch the orchestrator or frontend at all, so you can test it completely standalone: write a 
throwaway script that calls run_agent() directly with a real GitHub query and just prints whatever it yields. 
Verify by eye:
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

TOOLS = registry.orchestrator_tools()

async def run(model: str, messages: list[dict], think: bool):
    #planner_messages = [{"role": "system", "content": PLANNER_SYSTEM_PROMPT}, *messages]
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, *messages]

    """
    need to implement our own streaming responses here
    """

    call_rounds = 0
    MAX_ROUNDS = 5

    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            yield events.emit(events.plan_event("Thinking..."))

            while True:

                print("calling planner")
                plan = await ollama.chat(client, model, messages, think=False, tools=TOOLS)
                print("plan", plan)

                agents = plan["message"].get("tool_calls", [])

                if not agents:
                    print("no agents found, breaking")
                    break

                print("plan found", agents)

                call_rounds += 1
                if call_rounds > MAX_ROUNDS:
                    break

                for agent in agents:
                    agent_name = agent["function"]["name"]
                    agent_args = agent["function"]["arguments"]

                    try:
                        if isinstance(agent_args, str):
                            agent_args = json.loads(agent_args)
                    except json.JSONDecodeError as e:
                        messages.append({"role": "assistant", "tool_calls": [agent]})
                        messages.append({"role": "tool", "content": f"Malformed arguments: {e}"})
                        yield events.emit(events.agent_error_event(agent_name, f"Malformed arguments: {e}"))
                        continue

                    agent_config = registry.AGENTS.get(agent_name, None)

                    if not agent_config:
                        messages.append({"role": "assistant", "tool_calls": [agent]})
                        messages.append({"role": "tool", "content": f"Unknown agent: {agent_name}"})
                        yield events.emit(events.agent_error_event(agent_name, f"Unknown agent: {agent_name}"))
                        continue

                    query = agent_args.get("query")
                    if not query:
                        messages.append({"role": "assistant", "tool_calls": [agent]})
                        messages.append({"role": "tool", "content": "Missing required argument: query"})
                        yield events.emit(events.agent_error_event(agent_name, "Missing required argument: query"))
                        continue

                    yield events.emit(events.agent_start_event(agent_config.name))
                    start = time.perf_counter()

                    tool_history = []
                    result_content = None

                    agent_messages = [
                        {"role": "system", "content": agent_config.system_prompt},
                        {"role": "user", "content": query},
                    ]

                    try:
                        async for ev in run_agent(
                            agent_config.name, model, agent_messages,
                            agent_config.tools, agent_config.tool_map, think
                        ):
                            if ev["type"] == "tool_call":
                                yield events.emit(ev)
                                tool_history.append({"tool": ev["tool"], "args": ev["args"]})
                            elif ev["type"] == "agent_result":
                                result_content = ev["content"]
                            elif ev["type"] == "agent_error":
                                yield events.emit(ev)
                    except Exception as e:
                        yield events.emit(events.agent_error_event(agent_config.name, str(e)))
                        result_content = f"Agent failed: {e}"

                    yield events.emit(events.agent_end_event(
                        agent_config.name, tool_history, duration_ms=int((time.perf_counter() - start) * 1000),
                    ))

                    messages.append({"role": "assistant", "tool_calls": [agent]})
                    messages.append({"role": "tool", "content": result_content or ""})
            print("starting stream to front end")
            async for line in ollama.emit_token_stream(client, model, messages, think=think, tools=None):
                yield line
    except Exception as e:
        yield events.emit(events.agent_error_event("orchestrator", str(e)))
        yield events.emit(events.done_event())