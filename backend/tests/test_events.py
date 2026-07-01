import json
from agents.events import emit

def test_emit_serializes_token_event():
    line = emit({"type" : "token", "content" : "hi"})

    assert json.loads(line) == {"type" : "token", "content" : "hi"}


def test_emit_rejects_missing_type_key():
    import pytest
    with pytest.raises(KeyError):
        emit({"content": "no type field"})

def test_emit_serializes_plan_event():
    line = emit({"type" : "plan", "content" : "thinking...", "duration_ms" : 0})
    assert json.loads(line) == {"type" : "plan", "content" : "thinking...", "duration_ms" : 0}

def test_emit_serializes_agent_start_event():
    line = emit({"type" : "agent_start", "agent" : "github_agent"})
    assert json.loads(line) == {"type" : "agent_start", "agent" : "github_agent"}