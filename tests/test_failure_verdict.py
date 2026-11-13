"""Auto-draw counts a call as failed exactly when Hermes says so in the hook's public `status` argument, with
the exceptions Hermes' own loop makes: a guardrail refusal, and a terminal call that exited 0."""
import json

import pytest

from ub_fakes import make_store, sub

OK_TEXT = json.dumps({"content": "1|hello", "total_lines": 1})
FAIL_TEXT = json.dumps({"output": "", "exit_code": 1, "error": "Command failed with exit code 1"})


def hook(tmp_path):
    store = make_store(tmp_path)
    s = sub("settings").read(lambda k, d=None: {"autodraw": True}.get(k, d))
    return sub("autodraw").AutoDraw(lambda: store, lambda: s, lambda: None)


def test_status_error_counts_whatever_the_result_looks_like(tmp_path):
    h = hook(tmp_path)
    out = [h(tool_name="read_file", result=OK_TEXT, status="error", turn_id="t1", session_id="s") for _ in range(3)]
    assert out[:2] == [None, None] and out[2] is not None and "unblockbruecke_card" in out[2]


def test_status_ok_never_counts_even_for_an_error_shaped_result(tmp_path):
    h = hook(tmp_path)
    out = [h(tool_name="terminal", result=FAIL_TEXT, status="ok", turn_id="t1", session_id="s") for _ in range(5)]
    assert out == [None] * 5


def test_the_verdict_is_the_status():
    bridge = sub("bridge")
    assert bridge.failed("read_file", OK_TEXT, "error") is True
    assert bridge.failed("terminal", FAIL_TEXT, "ok") is False
    assert bridge.failed("terminal", FAIL_TEXT, "") is False


def test_a_guardrail_refusal_of_a_repeated_call_is_not_a_failure():
    refusal = json.dumps({"guardrail_refusal": True, "error": "Repeated identical read_file call refused."})
    assert sub("bridge").failed("read_file", refusal, "error") is False


def test_a_terminal_call_that_exited_0_is_not_a_failure_even_with_error_text(tmp_path):
    bridge = sub("bridge")
    warned = json.dumps({"output": "x", "exit_code": 0, "error": "warning: deprecated flag"})
    assert bridge.failed("terminal", warned, "error") is False
    assert bridge.failed("terminal", FAIL_TEXT, "error") is True
    assert bridge.failed("terminal", json.dumps({"output": "", "exit_code": -1, "error": "Blocked workdir"}), "error") is True
    h = hook(tmp_path)
    out = [h(tool_name="terminal", result=warned, status="error", turn_id="t1", session_id="s") for _ in range(4)]
    assert out == [None] * 4


J = json.dumps
SHAPES = [
    ("terminal", J({"output": "hi", "exit_code": 0, "error": None})),
    ("terminal", J({"output": "", "exit_code": 1, "error": None})),
    ("terminal", J({"output": "", "exit_code": -1, "error": "Blocked workdir", "status": "blocked"})),
    ("terminal", J({"output": "", "exit_code": None, "error": None, "status": "yielded_to_background"})),
    ("terminal", J({"output": "", "exit_code": -1, "error": "BLOCKED: denied", "user_summary": "You denied it"})),
    ("terminal", J({"output": "x", "exit_code": 0, "error": "warning: deprecated flag"})),
    ("terminal", J({"output": "x", "exit_code": None, "error": "no exit code"})),
    ("read_file", J({"error": "You already read this file", "guardrail_refusal": True})),
    ("read_file", "  " + J({"error": "Repeat", "guardrail_refusal": True})),
    ("write_file", J({"bytes_written": 10, "path": "/tmp/x"})),
    ("patch", J({"success": True, "diff": "..."})),
    ("patch", J({"success": False, "error": "old_string not found"})),
    ("web_extract", J({"results": [{"url": "u", "error": None}]})),
    ("custom", "Error: boom"),
    ("custom", "all fine"),
    ("process", J({"status": "timeout", "output": ""})),
    ("custom", J({"success": False, "message": "nope"})),
    ("browser_cdp", J({"result": {"error": "the page's own text"}})),
    ("custom", J({"done": 3, "failed": 0})),
    ("custom", "{not json"),
    ("custom", J({"error": "", "ok": True})),
]


@pytest.mark.parametrize("tool,result", SHAPES)
def test_the_verdict_matches_the_one_hermes_loop_counts(tool, result):
    """The verdict Hermes' loop guardrail counts (private, so this runs only where Hermes' source is
    importable), against auto-draw's verdict on the status the hook gets: "error" for a JSON object with a
    non-empty `error`, else that same loop verdict (`model_tools._tool_result_observer_fields`)."""
    display = pytest.importorskip("agent.display")
    hermes = bool(display._detect_tool_failure(tool, result)[0])
    try:
        data = json.loads(result)
    except ValueError:
        data = None
    status = "error" if (isinstance(data, dict) and data.get("error")) or hermes else "ok"
    assert sub("bridge").failed(tool, result, status) is hermes
