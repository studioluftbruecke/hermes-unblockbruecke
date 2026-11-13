"""M2: the agent tool, `/card`, the skill, and Eselsbrücke's break contract (constraint 12)."""
import json
from typing import Any, Callable, Optional

from ub_fakes import FakeCtx, sub


def ctx_for(tmp_path, **settings):
    ctx = FakeCtx(tmp_path / "data", settings)
    import ub_fakes

    ub_fakes.load_plugin().register(ctx)
    return ctx


def test_register_adds_tool_command_and_skill(tmp_path):
    ctx = ctx_for(tmp_path)
    assert set(ctx.tools) == {"unblockbruecke_card", "unblockbruecke_decks"}
    assert "card" in ctx.commands and ctx.skills == ["unblockbruecke"]
    desc = ctx.tools["unblockbruecke_card"]["schema"]["description"]
    for word in ("draw", "decks", "show", "journal", "rate", "stuck", "break", "agent-unblock", "unblockbruecke:unblockbruecke"):
        assert word in desc


def test_draw_each_context(tmp_path):
    ctx = ctx_for(tmp_path)
    stuck = ctx.call("unblockbruecke_card", action="draw", context="stuck")
    assert stuck["ok"] and stuck["deck"] == "agent-unblock" and stuck["face"] == "agent"
    assert stuck["card"]["directive"].startswith('::card{deck="agent-unblock"')
    human = ctx.call("unblockbruecke_card", action="draw", context="human")
    assert human["deck"] == "human-unblock" and human["face"] == "human"
    coding = ctx.call("unblockbruecke_card", action="draw", deck="coding")
    assert coding["deck"] == "coding" and coding["card"]["id"].startswith("co-")
    bad = ctx.call("unblockbruecke_card", action="draw", deck="music")
    assert bad["ok"] is False and bad["error"] == "unknown_deck" and "coding" in bad["message"]
    rows = sub("journal").draws(sub("store").Store(tmp_path / "data"))
    assert [r["by"] for r in rows] == ["agent", "agent", "agent"]


def test_decks_show_journal_rate(tmp_path):
    ctx = ctx_for(tmp_path)
    decks = ctx.call("unblockbruecke_card", action="decks")
    assert {d["deck"] for d in decks["decks"]} == {"agent-unblock", "human-unblock", "coding", "design", "shaders", "writing"}
    assert decks["autodraw"] == {"on": False, "decks": ["agent-unblock"]}
    shown = ctx.call("unblockbruecke_card", action="show", deck="agent-unblock", id="ag-03")
    assert shown["card"]["human"] == "What did all three attempts believe?"
    by_prefix = ctx.call("unblockbruecke_card", action="show", id="ag-03")
    assert by_prefix["card"]["deck"] == "agent-unblock"
    missing = ctx.call("unblockbruecke_card", action="show", deck="agent-unblock", id="ag-99")
    assert missing["error"] == "unknown_card"
    drawn = ctx.call("unblockbruecke_card", action="draw")
    rated = ctx.call("unblockbruecke_card", action="rate", draw_id=drawn["draw_id"], rating="helped")
    assert rated == {"ok": True, "rated": {"draw_id": drawn["draw_id"], "rating": "helped"}}
    journal = ctx.call("unblockbruecke_card", action="journal", limit=5)
    assert journal["draws"][0]["rating"] == "helped" and journal["totals"]["helped"] == 1
    assert ctx.call("unblockbruecke_card", action="rate", draw_id="x", rating="helped")["ok"] is False
    assert ctx.call("unblockbruecke_card", action="fly")["error"] == "unknown_action"


def test_rate_refused_unattended(tmp_path, monkeypatch):
    ctx = ctx_for(tmp_path)
    drawn = ctx.call("unblockbruecke_card", action="draw")
    monkeypatch.setattr(sub("bridge"), "_finite_turn", lambda: True)
    out = ctx.call("unblockbruecke_card", action="rate", draw_id=drawn["draw_id"], rating="helped")
    assert out["error"] == "unattended" and "Nothing was changed" in out["message"]


def test_unattended_draw_skips_human_cards_only_for_the_agent_itself(tmp_path, monkeypatch):
    ctx = ctx_for(tmp_path)
    monkeypatch.setattr(sub("bridge"), "_finite_turn", lambda: True)
    for _ in range(20):
        out = ctx.call("unblockbruecke_card", action="draw", deck="agent-unblock", context="stuck")
        assert "human" not in out["card"]["tags"] and "unattended" in out
    for_person = ctx.call("unblockbruecke_card", action="draw", deck="human-unblock", context="human")
    assert for_person["ok"] and "unattended" not in for_person  # a card for a person, read later
    only_human = ctx.call("unblockbruecke_card", action="draw", deck="human-unblock", context="stuck")
    assert only_human["error"] == "no_card" and "nobody is at the keyboard" in only_human["message"]


def test_handler_never_raises(tmp_path, monkeypatch):
    ctx = ctx_for(tmp_path)
    monkeypatch.setattr(sub("service"), "draw_card", lambda *a, **k: 1 / 0)
    out = ctx.call("unblockbruecke_card", action="draw")
    assert out["ok"] is False and out["error"] == "internal" and "ZeroDivisionError" in out["message"]


def test_card_command(tmp_path):
    ctx = ctx_for(tmp_path)
    handler = ctx.commands["card"]
    text = handler("coding", session_id="s-9")
    assert text.startswith("Coding · co-") and "For an agent" not in text
    agent = handler("agent")
    assert agent.startswith("Agent · ag-") and "For an agent: " in agent
    assert handler("").count("\n") == 1
    assert "coding (" in handler("decks")
    assert "no deck named music" in handler("music")
    rows = sub("journal").draws(sub("store").Store(tmp_path / "data"))
    assert rows[-1]["session_id"] == "s-9" and {r["by"] for r in rows} == {"user"}


# --- Eselsbrücke's contract (R26 there), copied from feat/eselsbruecke/v0.1 plugins/eselsbruecke/tips.py
CARD_TOOL = "unblockbruecke_card"
CARD_ARGS = {"action": "draw", "context": "break"}


def pick_tip(user_tips=None, seed=None):
    return {"source": "builtin", "title": "Stand up", "why": "tip"}


def break_tip(has_tool: Callable[[str], bool], dispatch: Callable[[str, dict], Any],
              user_tips: Optional[list] = None, seed: Optional[int] = None) -> dict:
    """{"source": "unblockbruecke"|"builtin"|"user", "title", "text"}; never raises."""
    try:
        if has_tool(CARD_TOOL):
            answer = dispatch(CARD_TOOL, dict(CARD_ARGS))
            if isinstance(answer, str):
                answer = json.loads(answer)
            if (isinstance(answer, dict) and isinstance(answer.get("title"), str) and answer["title"].strip()
                    and isinstance(answer.get("text"), str)):
                return {"source": "unblockbruecke", "title": answer["title"][:200], "text": answer["text"][:600]}
    except Exception:
        pass
    tip = pick_tip(user_tips, seed)
    return {"source": tip["source"], "title": tip["title"], "text": tip.get("why", "")}
# --- end of the copy


def test_eselsbruecke_break_gets_a_human_card(tmp_path):
    ctx = ctx_for(tmp_path)
    handler = ctx.tools[CARD_TOOL]["handler"]
    got = break_tip(lambda name: name in ctx.tools, lambda name, args: handler(args))
    assert got["source"] == "unblockbruecke"
    human = {c["human"] for c in sub("decks").SHIPPED["human-unblock"]["cards"]}
    assert got["title"] in human and got["text"]
    answer = json.loads(handler(dict(CARD_ARGS)))
    assert answer["face"] == "human" and answer["deck"] == "human-unblock"


def test_eselsbruecke_falls_back_when_off_or_broken(tmp_path):
    assert break_tip(lambda name: False, lambda n, a: None)["source"] == "builtin"
    assert break_tip(lambda name: True, lambda n, a: json.dumps({"ok": False, "error": "no_card"}))["source"] == "builtin"
