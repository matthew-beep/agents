import json
import pytest
from agents.events import emit, plan_event, agent_start_event, tool_call_event, agent_end_event, token_event, done_event


# test that emit rejects missing type key
def test_emit_rejects_missing_type_key():
    with pytest.raises(KeyError):
        emit({"content": "no type field"})
        
# test that emit serializes token event
def test_emit_serializes_token_event():
    line = emit({"type" : "token", "content" : "hi"})

    assert json.loads(line) == {"type" : "token", "content" : "hi"}

# test that emit serializes plan event
def test_emit_serializes_plan_event():
    line = emit({"type" : "plan", "content" : "thinking...", "duration_ms" : 0})
    assert json.loads(line) == {"type" : "plan", "content" : "thinking...", "duration_ms" : 0}

# test that emit serializes agent start event
def test_emit_serializes_agent_start_event():
    line = emit({"type" : "agent_start", "agent" : "github_agent"})
    assert json.loads(line) == {"type" : "agent_start", "agent" : "github_agent"}

# test that emit serializes agent end event
def test_emit_serializes_agent_end_event():
    line = emit({"type" : "agent_end", "agent" : "github_agent", "tools" : [{"tool" : "search_repos", "args" : {"query" : "python"}}]})
    assert json.loads(line) == {"type" : "agent_end", "agent" : "github_agent", "tools" : [{"tool" : "search_repos", "args" : {"query" : "python"}}]}

# test that emit serializes tool call event
def test_emit_serializes_tool_call_event():
    line = emit({"type" : "tool_call", "tool" : "search_repos", "args" : {"query" : "python"}, "duration_ms" : 100})
    assert json.loads(line) == {"type" : "tool_call", "tool" : "search_repos", "args" : {"query" : "python"}, "duration_ms" : 100}

# test that emit serializes done event
def test_emit_serializes_done_event():
    line = emit({"type" : "done", "tokens" : 100, "tokens_per_sec" : 0, "duration_ms" : 100, "total_ms" : 100})
    assert json.loads(line) == {"type" : "done", "tokens" : 100, "tokens_per_sec" : 0, "duration_ms" : 100, "total_ms" : 100}

# --- 

# test that plan_event returns the correct event
def test_plan_event():
    event = plan_event("planning", duration_ms=100)
    assert event == {"type" : "plan", "content" : "planning", "duration_ms" : 100}


# test that agent_start_event returns the correct event
def test_agent_start_event():
    event = agent_start_event("github_agent")
    assert event == {"type" : "agent_start", "agent" : "github_agent"}

# test tool_call_event returns correct tool call
def test_tool_call_event():
    event_with_duration = tool_call_event("search_repos", {"query" : "python"}, duration_ms=100)
    event_without_duration = tool_call_event("search_repos", {"query" : "python"})
    assert event_with_duration == {"type":"tool_call", "tool" : "search_repos", "args" : {"query" : "python"}, "duration_ms" : 100} and event_without_duration == {"type":"tool_call", "tool" : "search_repos", "args" : {"query" : "python"}}

def test_agent_end_event():
    event_with_duration = agent_end_event("github_agent", [{"tool" : "search_repos", "args" : {"query" : "python"}}], duration_ms=100)
    event_without_duration = agent_end_event("github_agent", [{"tool" : "search_repos", "args" : {"query" : "python"}}], duration_ms=None)
    assert event_with_duration == {"type":"agent_end", "agent" : "github_agent", "tools" : [{"tool" : "search_repos", "args" : {"query" : "python"}}], "duration_ms" : 100} and event_without_duration == {"type":"agent_end", "agent" : "github_agent", "tools" : [{"tool" : "search_repos", "args" : {"query" : "python"}}]}

def test_token_event():
    event = token_event("hi")
    assert event == {"type" : "token", "content" : "hi"}

def test_done_event():
    event_with_tokens = done_event(tokens=100)

    assert event_with_tokens == {"type" : "done", "tokens" : 100}