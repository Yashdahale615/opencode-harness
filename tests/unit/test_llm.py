"""Unit tests for harness.llm.gemini (parser and data contracts only).

These tests do NOT call the Gemini API — they test the response parser
and ToolAction construction with synthetic model output.
"""
import json
import pytest
from harness.llm.gemini import ToolAction, _parse_response


# ---------------------------------------------------------------------------
# _parse_response
# ---------------------------------------------------------------------------

def response_json(**kwargs) -> str:
    data = {"explanation": "test", "actions": [], **kwargs}
    return json.dumps(data)


def test_parse_valid_edit():
    raw = json.dumps({
        "explanation": "write hello world",
        "actions": [
            {"kind": "edit", "path": "hello.py", "content": "print('hi')",
             "description": "create hello.py"},
        ],
    })
    actions, expl = _parse_response(raw)
    assert expl == "write hello world"
    assert len(actions) == 1
    assert actions[0].kind == "edit"
    assert actions[0].path == "hello.py"
    assert actions[0].content == "print('hi')"


def test_parse_valid_shell():
    raw = json.dumps({
        "explanation": "run tests",
        "actions": [
            {"kind": "shell", "argv": ["/usr/bin/pytest", "tests/"],
             "description": "run pytest"},
        ],
    })
    actions, _ = _parse_response(raw)
    assert actions[0].kind == "shell"
    assert actions[0].argv == ["/usr/bin/pytest", "tests/"]


def test_parse_done_action():
    raw = json.dumps({
        "explanation": "done",
        "actions": [{"kind": "done", "description": "all complete"}],
    })
    actions, _ = _parse_response(raw)
    assert actions[0].kind == "done"


def test_parse_invalid_json_returns_done():
    actions, expl = _parse_response("this is not json")
    assert actions[0].kind == "done"
    assert "parse_error" in actions[0].description


def test_parse_json_with_markdown_fences():
    raw = "```json\n" + json.dumps({
        "explanation": "fenced",
        "actions": [{"kind": "done"}],
    }) + "\n```"
    actions, expl = _parse_response(raw)
    assert expl == "fenced"
    assert actions[0].kind == "done"


def test_parse_empty_actions_list():
    raw = json.dumps({"explanation": "nothing", "actions": []})
    actions, _ = _parse_response(raw)
    # Should return a synthetic "no actions" done action
    assert len(actions) == 1
    assert actions[0].kind == "done"


def test_parse_multiple_actions():
    raw = json.dumps({
        "explanation": "do stuff",
        "actions": [
            {"kind": "read",  "path": "src/main.py", "description": "read file"},
            {"kind": "edit",  "path": "src/main.py", "content": "x=1", "description": "edit"},
            {"kind": "shell", "argv": ["/bin/true"], "description": "check"},
            {"kind": "done",  "description": "done"},
        ],
    })
    actions, _ = _parse_response(raw)
    assert [a.kind for a in actions] == ["read", "edit", "shell", "done"]


def test_tool_action_defaults():
    a = ToolAction(kind="edit", argv=[])
    assert a.path == ""
    assert a.content == ""
    assert a.description == ""


def test_client_raises_without_api_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    from harness.llm.gemini import GeminiClient
    with pytest.raises(EnvironmentError, match="GEMINI_API_KEY"):
        GeminiClient()
