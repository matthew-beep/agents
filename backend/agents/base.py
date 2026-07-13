import httpx
import json
from agents import ollama, events
from collections.abc import AsyncIterator



AGENT_MAX_ROUNDS = 5

# Async generator. Yields `tool_call` events live as domain tools fire, and a final
# `agent_result` the orchestrator captures — it does not stream to the frontend itself.
async def run_agent(
    name: str,
    model: str,
    messages: list[dict],
    tools: list,
    tool_map: dict,
    think: bool,
    client: httpx.AsyncClient,
) -> AsyncIterator[dict]:

    print(f"[{name}] starting")
    rounds = 0
    while True:

        # get response from agent
        resp = await ollama.chat(client, model, messages, think=think, tools=tools)
        msg = resp.get("message", {})

        tool_calls = msg.get("tool_calls", [])

        # No tool calls means this is the final response — collect and return.
        if not tool_calls:
            print(f"[{name}] done")
            yield events.agent_result_event(msg.get("content", ""))
            return

        rounds += 1
        if rounds > AGENT_MAX_ROUNDS:
            print(f"[{name}] max rounds reached")
            partial = msg.get("content") or ""
            yield events.agent_result_event(
                f"Stopped after {AGENT_MAX_ROUNDS} tool rounds without a final answer. {partial}".strip()
            )
            return


        print(f"[{name}] tool calls: {[tc['function']['name'] for tc in tool_calls]}")

        assistant_msg = {"role": "assistant", "tool_calls": tool_calls}
        if msg.get("content"):
            assistant_msg["content"] = msg["content"]
        messages.append(assistant_msg)
        for tc in tool_calls:
            fn_name = tc["function"]["name"]
            fn_args = tc["function"]["arguments"]
            fn = tool_map.get(fn_name)

            try:
                if isinstance(fn_args, str):
                    fn_args = json.loads(fn_args)
                # Record before executing so the orchestrator can surface this to the frontend.
                print(f"[{name}] calling {fn_name} with {fn_args}")
                yield events.tool_call_event(fn_name, fn_args)
                result = await fn(client=client, **fn_args) if fn else f"unknown tool: {fn_name}"
                print(f"[{name}] {fn_name} result: {str(result)[:120]}")
            except Exception as e:
                print(f"[{name}] error calling {fn_name}: {e}")
                yield events.agent_error_event(name, str(e), tool=fn_name)
                result = f"Tool failed: {e}"


            content = result if isinstance(result, str) else json.dumps(result)
            messages.append({"role": "tool", "content": content, "tool_name": fn_name})
