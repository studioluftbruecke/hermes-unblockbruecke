"""The reply of a turn where Hermes drew a card names that card in one line, added by
`transform_llm_output` without the model: a card directive on Desktop, a plain line elsewhere, nothing
on every other turn, once per turn, fail-open."""
import json

import pytest

from ub_fakes import FakeCtx, load_plugin, sub

FAIL = json.dumps({"output": "boom", "exit_code": 1, "error": None})


def ctx_for(tmp_path, autodraw=True):
    ctx = FakeCtx(tmp_path / "data", {"autodraw": autodraw})
    load_plugin().register(ctx)
    return ctx


def fail_turn(ctx, turn, n=3):
    hook = ctx.hooks["transform_tool_result"]
    return [hook(tool_name="terminal", result=FAIL, status="error", turn_id=turn, session_id="s") for _ in range(n)]


def drawn(ctx):
    row = sub("journal").draws(load_plugin().make_store(ctx))[0]
    return row["deck"], row["card"]


def test_desktop_reply_gets_the_card_directive_once(tmp_path):
    ctx = ctx_for(tmp_path)
    fail_turn(ctx, "t1")
    deck, card = drawn(ctx)
    reply = ctx.hooks["transform_llm_output"]
    out = reply(response_text="The registry is down; I used the mirror.\n", platform="desktop", session_id="s", turn_id="t1")
    assert out == f'The registry is down; I used the mirror.\n\n::card{{deck="{deck}" id="{card}"}}'
    assert reply(response_text="again", platform="desktop", turn_id="t1") is None  # once per turn


def test_other_surfaces_get_a_plain_line(tmp_path):
    ctx = ctx_for(tmp_path)
    fail_turn(ctx, "t1")
    deck, card = drawn(ctx)
    human = next(c["human"] for c in sub("decks").SHIPPED[deck]["cards"] if c["id"] == card)
    out = ctx.hooks["transform_llm_output"](response_text="Done.", platform="cli", turn_id="t1")
    assert out == f"Done.\n\nUnblockbrücke drew a card for Hermes: {human} ({card})"
    assert "::card{" not in out


def test_turns_without_a_card_are_left_alone(tmp_path):
    ctx = ctx_for(tmp_path)
    fail_turn(ctx, "t1", n=2)
    reply = ctx.hooks["transform_llm_output"]
    assert reply(response_text="Fine.", platform="desktop", turn_id="t1") is None
    assert reply(response_text="Fine.", platform="desktop", turn_id="") is None
    off = ctx_for(tmp_path / "off", autodraw=False)
    fail_turn(off, "t1")
    assert off.hooks["transform_llm_output"](response_text="Fine.", platform="desktop", turn_id="t1") is None


def test_an_empty_reply_gets_no_line_and_the_hook_fails_open(tmp_path):
    ctx = ctx_for(tmp_path)
    fail_turn(ctx, "t1")
    reply = ctx.hooks["transform_llm_output"]
    assert reply(response_text="  ", platform="desktop", turn_id="t1") is None
    assert reply(response_text=None, platform="desktop", turn_id="t2") is None
    assert reply() is None


def test_manifest_lists_both_hooks():
    from ruamel.yaml import YAML

    from ub_fakes import ROOT

    manifest = YAML(typ="safe", pure=True).load((ROOT / "plugin.yaml").read_text(encoding="utf-8"))
    assert manifest["provides_hooks"] == ["transform_tool_result", "transform_llm_output"]


@pytest.mark.parametrize("unattended", ["cron", "webhook", "single query"])
def test_a_turn_nobody_reads_gets_no_reply_line(tmp_path, monkeypatch, unattended):
    """Hermes keeps only the first reply rewrite of a turn, so the line is added only where a person reads
    the reply; in a scheduled job, a webhook or a single-query run another plugin's rewrite keeps the turn."""
    ctx = ctx_for(tmp_path)
    if unattended == "cron":
        ctx.current_cron_execution = lambda: {"job_id": "j1"}
    elif unattended == "webhook":
        ctx.surface = "webhook"
    else:
        monkeypatch.setenv("HERMES_SINGLE_QUERY_SESSION", "1")
    fail_turn(ctx, "t1")
    assert ctx.hooks["transform_llm_output"](response_text="Report.", platform="cron", turn_id="t1") is None
