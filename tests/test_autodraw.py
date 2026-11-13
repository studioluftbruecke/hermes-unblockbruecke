"""Auto-draw. Attach on real result shapes, Hermes' own failure verdict before and after the card,
the window (N failed of the last N + 2 calls), once per turn, concurrency, the LRU, unattended,
fail-open, settings, timing.

The tests marked `hermes` run Hermes' real `agent.display._detect_tool_failure`, which Hermes applies
to the result after the hook; they are skipped where Hermes is not importable.
"""
import json
import re
import threading
import time
from pathlib import Path

import pytest

from ub_fakes import FakeCtx, load_plugin, make_store, sub

try:
    from agent.display import _detect_tool_failure as HERMES_DETECT  # type: ignore
except Exception:  # the plain test venv has no Hermes
    HERMES_DETECT = None

hermes = pytest.mark.skipif(HERMES_DETECT is None, reason="Hermes (agent.display) is not importable here")

# Recorded result shapes (real sessions and Hermes' own tools).
TERMINAL_FAIL = json.dumps({"output": "Error: Cannot find module @rollup/rollup-linux-arm64-gnu", "exit_code": 1,
                            "error": "Command failed with exit code 1"})
TERMINAL_OK_WITH_ERROR_TEXT = json.dumps({"output": "warning only", "exit_code": 0, "error": "deprecated flag"})
READ_FILE_FAIL = json.dumps({"error": "File not found: /tmp/x/NOTES.md"})
PLUGIN_FAIL = json.dumps({"ok": False, "error": "upstream_timeout", "message": "stamp registry timed out after 10 s"})
SUCCESS_FALSE = json.dumps({"success": False, "error": "Skill 'x' not found."})
GUARDRAIL_REFUSAL = json.dumps({"guardrail_refusal": True, "error": "Repeated identical read_file call refused."})
PLAIN_FAIL = "Error: request to https://registry.stamps.internal timed out"
OK_RESULT = json.dumps({"content": "1|hello", "total_lines": 1})
FAILING_SHAPES = [("terminal", TERMINAL_FAIL), ("read_file", READ_FILE_FAIL), ("stamp_lookup", PLUGIN_FAIL),
                  ("skill_view", SUCCESS_FALSE), ("web_extract", PLAIN_FAIL)]


def card():
    return {"deck": "agent-unblock", "deck_name": "Agent unblock", "id": "ag-03", "human": "What did all three attempts believe?",
            "agent": "Name the one assumption your last three attempts shared, then test that assumption directly."}


def test_attach_json_object_adds_one_key_and_keeps_the_rest():
    ad = sub("autodraw")
    out = ad.attach(TERMINAL_FAIL, card(), 3)
    data = json.loads(out)
    assert data["exit_code"] == 1 and data["error"] == "Command failed with exit code 1"
    assert data["unblockbruecke_card"] == {"card": card()["agent"], "note": ad.note(3, 3)}
    assert "not an order" in data["unblockbruecke_card"]["note"]
    assert {k: v for k, v in data.items() if k != "unblockbruecke_card"} == json.loads(TERMINAL_FAIL)


def test_attach_plain_text_appends_one_line():
    ad = sub("autodraw")
    out = ad.attach(PLAIN_FAIL, card(), 3)
    assert out.startswith(PLAIN_FAIL) and out.count("\n") == 2
    assert out.endswith("A nudge, not an order.)") and f"[unblockbruecke] {card()['agent']} (3 of your last 5" in out


@pytest.mark.parametrize("shape", [None, {"error": "x"}, "[1, 2]", "{not json", json.dumps({"unblockbruecke_card": 1})])
def test_attach_leaves_other_shapes_alone(shape):
    assert sub("autodraw").attach(shape, card(), 3) is None


@hermes
@pytest.mark.parametrize("tool,result", FAILING_SHAPES)
def test_hermes_still_counts_the_call_as_failed_after_the_card(tool, result):
    """The card never hides the failure, through Hermes' own function."""
    before = HERMES_DETECT(tool, result)[0]
    after = HERMES_DETECT(tool, sub("autodraw").attach(result, card(), 3))[0]
    assert before is True and after is True


@hermes
def test_appended_prose_would_have_hidden_the_failure():
    """As a guard: the naive design flips Hermes' verdict, ours does not."""
    naive = TERMINAL_FAIL + "\n\n[unblockbruecke] card text"
    assert HERMES_DETECT("terminal", naive)[0] is False
    assert HERMES_DETECT("terminal", sub("autodraw").attach(TERMINAL_FAIL, card(), 3))[0] is True


def hook_for(tmp_path, settings=None, unattended=None):
    ad = sub("autodraw")
    store = make_store(tmp_path)
    s = sub("settings").read(lambda k, d=None: (settings or {}).get(k, d))
    return ad.AutoDraw(lambda: store, lambda: s, unattended or (lambda: None)), store


def fail_calls(hook, n, turn="t1", tool="terminal", result=TERMINAL_FAIL):
    return [hook(tool_name=tool, result=result, status="error", turn_id=turn, session_id="s1") for _ in range(n)]


def test_off_by_default_changes_nothing(tmp_path):
    hook, store = hook_for(tmp_path)
    assert fail_calls(hook, 5) == [None] * 5
    assert store.listdir("journal") == []


def test_third_failure_carries_one_card_and_the_turn_stays_quiet(tmp_path):
    hook, store = hook_for(tmp_path, {"autodraw": True})
    out = fail_calls(hook, 6)
    assert out[0] is None and out[1] is None and out[2] is not None
    assert out[3:] == [None, None, None]  # once per turn
    card_ = json.loads(out[2])["unblockbruecke_card"]
    rows = sub("journal").draws(store)
    assert card_["draw_id"] == rows[0]["draw_id"] and rows[0]["deck"] == "agent-unblock" and rows[0]["card"].startswith("ag-")
    assert len(rows) == 1 and rows[0]["by"] == "auto" and rows[0]["streak"] == 3 and rows[0]["attached"] is True
    assert rows[0]["tool"] == "terminal" and rows[0]["turn_id"] == "t1"
    assert "args" not in rows[0]
    assert fail_calls(hook, 3, turn="t2")[2] is not None  # a new turn has its own budget


def test_a_success_no_longer_resets_and_outcomes_are_recorded(tmp_path):
    """0.2: 3 failed among the last 5 calls; a success between failures does not start over."""
    hook, store = hook_for(tmp_path, {"autodraw": True})
    fail_calls(hook, 2)
    assert hook(tool_name="read_file", result=OK_RESULT, status="ok", turn_id="t1") is None
    out = fail_calls(hook, 1)
    assert out[0] is not None  # F F ok F: 3 of the last 4
    fail_calls(hook, 1)
    hook(tool_name="read_file", result=OK_RESULT, status="ok", turn_id="t1")
    row = sub("journal").draws(store)[0]
    assert row["next"] == {"status": "failed", "tool": "terminal", "calls_to_recover": 2}


def test_any_tools_count_across(tmp_path):
    hook, _ = hook_for(tmp_path, {"autodraw": True})
    a = hook(tool_name="terminal", result=TERMINAL_FAIL, status="error", turn_id="t")
    b = hook(tool_name="read_file", result=READ_FILE_FAIL, status="error", turn_id="t")
    c = hook(tool_name="web_extract", result=PLAIN_FAIL, status="error", turn_id="t")
    assert a is None and b is None and c is not None and "[unblockbruecke]" in c


def test_refusals_never_build_a_streak(tmp_path):
    hook, _ = hook_for(tmp_path, {"autodraw": True})
    assert fail_calls(hook, 5, tool="read_file", result=GUARDRAIL_REFUSAL) == [None] * 5


def test_threshold_is_clamped_and_one_card_per_turn(tmp_path):
    hook, _ = hook_for(tmp_path, {"autodraw": True, "autodraw_threshold": 2, "autodraw_per_turn": 2})
    out = fail_calls(hook, 6)
    assert [o is not None for o in out] == [False, True, False, False, False, False]  # 0.2: one per turn
    hook2, _ = hook_for(tmp_path, {"autodraw": True, "autodraw_threshold": 99})
    out2 = fail_calls(hook2, 7, turn="x")
    assert [o is not None for o in out2].index(True) == 5  # clamped to 6
    assert sum(o is not None for o in out2) == 1


def test_concurrent_failures_give_exactly_one_card(tmp_path):
    hook, store = hook_for(tmp_path, {"autodraw": True})
    results = []
    lock = threading.Lock()

    def call():
        r = hook(tool_name="terminal", result=TERMINAL_FAIL, status="error", turn_id="par")
        with lock:
            results.append(r)

    threads = [threading.Thread(target=call) for _ in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sum(r is not None for r in results) == 1
    assert len(sub("journal").draws(store)) == 1


def test_lru_keeps_512_turns():
    ad = sub("autodraw")
    tr = ad.Tracker(size=512)
    for i in range(600):
        tr.step(f"t{i}", True, 3)
    assert len(tr.turns) == 512 and "t0" not in tr.turns and "t599" in tr.turns


def test_unattended_skips_human_cards_and_logs_skipped(tmp_path, monkeypatch):
    from ub_fakes import card as make_card, deck_doc, write_user_deck

    decks = sub("decks")
    # Only cards that ask a person are left for Hermes: a deck of `auto` + `human` cards, the Agent deck off.
    hook, store = hook_for(tmp_path, {"autodraw": True}, unattended=lambda: "a single-query run (hermes chat -q or -z)")
    write_user_deck(store, deck_doc("ask", prefix="as", cards=[make_card(n, "as", tags=["auto", "human"]) for n in (1, 2)]))
    sub("service").ensure_seed(store, {})
    decks.set_switch(store, "agent-unblock", auto=False)
    decks.set_switch(store, "ask", auto=True)
    out = fail_calls(hook, 3)
    assert out == [None, None, None]
    rows, _ = store.read_jsonl("journal", "2026-11.jsonl")
    assert rows[-1]["kind"] == "skipped" and rows[-1]["reason"] == "unattended"
    attended, _ = hook_for(tmp_path, {"autodraw": True})
    assert fail_calls(attended, 3, turn="t9")[2] is not None


def test_imported_decks_are_off_for_auto_draw(tmp_path):
    from ub_fakes import deck_doc, write_user_deck

    from ub_fakes import card as make_card

    hook, store = hook_for(tmp_path, {"autodraw": True})
    write_user_deck(store, deck_doc("bought", prefix="bo", cards=[make_card(n, "bo", tags=["auto"]) for n in (1, 2)]))
    sub("decks").set_switch(store, "bought", source="imported")
    sub("service").ensure_seed(store, {})
    sub("decks").set_switch(store, "agent-unblock", auto=False)
    assert fail_calls(hook, 3) == [None, None, None]
    sub("decks").set_switch(store, "bought", auto=True)
    assert fail_calls(hook, 3, turn="t2")[2] is not None


def test_hook_fails_open(tmp_path):
    ad = sub("autodraw")

    def boom():
        raise RuntimeError("settings unreadable")

    hook = ad.AutoDraw(lambda: make_store(tmp_path), boom, lambda: None)
    assert hook(tool_name="terminal", result=TERMINAL_FAIL, status="error", turn_id="t") is None
    hook2, _ = hook_for(tmp_path, {"autodraw": True})
    hook2.store_factory = boom
    assert fail_calls(hook2, 3) == [None, None, None]


def test_no_turn_key_and_own_tool_are_ignored(tmp_path):
    hook, _ = hook_for(tmp_path, {"autodraw": True})
    assert [hook(tool_name="terminal", result=TERMINAL_FAIL, status="error") for _ in range(4)] == [None] * 4
    assert fail_calls(hook, 4, tool="unblockbruecke_card") == [None] * 4


def test_session_id_alone_is_not_a_turn(tmp_path):
    """A call with a session_id but no turn_id is skipped (see test_agent_surface.py)."""
    hook, _ = hook_for(tmp_path, {"autodraw": True})
    out = [hook(tool_name="terminal", result=TERMINAL_FAIL, status="error", session_id="only-session") for _ in range(3)]
    assert out == [None, None, None]


def test_draw_is_fast(tmp_path):
    """Constraint 4: the draw is a file read and an append, under 5 ms. The fastest of 20 draws is the
    code's own cost; the median also carries the host's load (a shared host runs other work), so it only
    guards against a gross regression. Numbers with the load: runs/m3-timing.txt."""
    hook, _ = hook_for(tmp_path, {"autodraw": True})
    fail_calls(hook, 3, turn="warm")
    times = []
    for i in range(20):
        fail_calls(hook, 3, turn=f"t{i}")
        times.append(hook.last_ms)
    times.sort()
    assert times[0] < 5.0 and times[len(times) // 2] < 25.0, times


def test_defaults_match_plugin_yaml():
    settings = sub("settings")
    text = (Path(settings.__file__).resolve().parent / "plugin.yaml").read_text(encoding="utf-8")
    from ruamel.yaml import YAML

    schema = YAML(typ="safe").load(text)["config_schema"]
    assert set(schema) == set(settings.DEFAULTS) - settings.RETIRED
    assert settings.RETIRED == {"show_in_sidebar", "autodraw_decks"} and not settings.RETIRED & set(schema)
    for key, spec in schema.items():
        assert spec["default"] == settings.DEFAULTS[key], key
    assert settings.read(lambda k, d=None: None) == settings.DEFAULTS


def test_register_wires_the_hook(tmp_path):
    ctx = FakeCtx(tmp_path / "data", {"autodraw": True})
    load_plugin().register(ctx)
    assert "transform_tool_result" in ctx.hooks
