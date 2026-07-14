import httpx
import json
import time
from agents import ollama, events, registry
from agents.base import run_agent

SYSTEM_PROMPT = f"""You are a helpful assistant. Be concise and direct.

You have access to specialized agents that can fetch real data:
{registry.agent_directory()}

If you can answer from your own knowledge, do so. Only call an agent when you need live data."""



TOOLS = registry.orchestrator_tools()

async def run(model: str, messages: list[dict], think: bool):
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, *messages]

    call_rounds = 0
    MAX_ROUNDS = 5

    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            yield events.emit(events.thinking_event())

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
                        messages.append({"role": "tool", "content": f"Malformed arguments: {e}", "tool_name": agent_name})
                        yield events.emit(events.agent_error_event(agent_name, f"Malformed arguments: {e}"))
                        continue

                    agent_config = registry.AGENTS.get(agent_name, None)

                    if not agent_config:
                        messages.append({"role": "assistant", "tool_calls": [agent]})
                        messages.append({"role": "tool", "content": f"Unknown agent: {agent_name}", "tool_name": agent_name})
                        yield events.emit(events.agent_error_event(agent_name, f"Unknown agent: {agent_name}"))
                        continue

                    query = agent_args.get("query")
                    if not query:
                        messages.append({"role": "assistant", "tool_calls": [agent]})
                        messages.append({"role": "tool", "content": "Missing required argument: query", "tool_name": agent_name})
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
                            agent_config.tools, agent_config.tool_map, think, client
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
                    messages.append({"role": "tool", "content": result_content or "", "tool_name": agent_config.name})
            print("starting stream to front end")
            async for line in ollama.emit_token_stream(client, model, messages, think=think, tools=None):
                yield line
    except Exception as e:
        yield events.emit(events.agent_error_event("orchestrator", str(e)))
        yield events.emit(events.done_event())