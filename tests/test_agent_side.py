"""M2 'The agent's side' (PLAN-v0.2): the window rule, one card per turn, only `auto` cards from decks
whose Hermes switch is on (seeded once from a stored `autodraw_decks`), the matched-tag preference, the
short payload, journal rows with where the turn ran and the next call's status as a fact.

The four SILENT patterns of `review-v0.2/agent_experience.py` run through the registered hook. Three
are red on 0.1.0 and 0.1.4 (no card); the fourth ("two failures per turn over five turns") stays silent
by decision: M0 P1 found no fire that carrying the count across turns adds, so the count stays per turn
(D17 not supported). Evidence: `experiments/unblockbruecke/v0.2/core/m2_*.out`.
"""
import json

import pytest

from ub_fakes import FakeCtx, deck_doc, load_plugin, make_store, sub, write_user_deck

FAIL = json.dumps({"output": "pytest: 3 failed, 41 passed", "exit_code": 1, "error": None})
OK = json.dumps({"output": "ok", "exit_code": 0, "error": None})
PATCHED = json.dumps({"success": True, "diff": "..."})
READ_OK = json.dumps({"content": "1|hello", "total_lines": 1})
TIMEOUT = json.dumps({"error": "stamp registry unreachable: upstream timeout after 30 s", "release": "4.2"})
TEXT_FAIL = "Error: connection refused"
FAILING = (FAIL, TIMEOUT, TEXT_FAIL)
REFRAME = {"ag-04", "ag-07", "ag-20"}  # the Agent deck's `reframe` cards (M0 P5's matched pool)


@pytest.fixture(autouse=True)
def no_session_markers(monkeypatch):
    """The test process may run inside a Hermes session: its markers must not decide `where`."""
    for var in ("HERMES_SESSION_SOURCE", "HERMES_SESSION_PLATFORM", "HERMES_KANBAN_TASK", "HERMES_CRON_SESSION",
                "HERMES_SINGLE_QUERY_SESSION", "HERMES_PLUGIN_HOST_PROCESS"):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture(autouse=True)
def detector():
    bridge = sub("bridge")
    bridge.set_detector(lambda tool, result: (isinstance(result, str) and result in FAILING, ""))
    yield
    bridge.set_detector(None)


def ctx_with(tmp_path, surface="desktop", **settings):
    ctx = FakeCtx(tmp_path / f"data-{len(list(tmp_path.iterdir()))}", {"autodraw": True, **settings}, surface=surface)
    load_plugin().register(ctx)
    return ctx


def run(ctx, turn, calls):
    hook = ctx.hooks["transform_tool_result"]
    return [hook(tool_name=t, args={}, result=r, status="error" if r in FAILING else "ok", turn_id=turn,
                 session_id="s1") for t, r in calls]


def cards(outs):
    return sum(1 for o in outs if o is not None)


def store_of(ctx):
    return load_plugin().make_store(ctx)


# --- the four SILENT patterns (AX-1) -------------------------------------------------------------------

def test_fix_rerun_fail_gets_a_card(tmp_path):
    """An edit lands between each failing test run, six rounds: 0.1 gave no card."""
    outs = run(ctx_with(tmp_path), "t", [("terminal", FAIL), ("patch", PATCHED)] * 6)
    assert cards(outs) == 1 and outs[4] is not None  # the third failure, two edits between


def test_fail_look_fail_gets_a_card(tmp_path):
    """A read between each failure, six rounds: 0.1 gave no card."""
    outs = run(ctx_with(tmp_path), "t", [("terminal", FAIL), ("read_file", READ_OK)] * 6)
    assert cards(outs) == 1 and outs[4] is not None


def test_two_failures_one_good_call_gets_a_card(tmp_path):
    """Two failures, one good call, five times: 0.1 gave no card."""
    outs = run(ctx_with(tmp_path), "t", [("terminal", FAIL), ("terminal", FAIL), ("terminal", OK)] * 5)
    assert cards(outs) == 1 and outs[3] is not None  # F F ok F: 3 of the last 4


def test_two_failures_per_turn_stay_silent_by_decision(tmp_path):
    """The person says 'still broken' five times, two failures each turn: the count stays per turn
    (M0 P1, D17 not supported), so no card. Green on 0.1 too; this pins the decision."""
    ctx = ctx_with(tmp_path)
    assert sum(cards(run(ctx, f"turn-{n}", [("terminal", FAIL)] * 2)) for n in range(5)) == 0


def test_the_window_forgets_old_failures(tmp_path):
    """3 of the last 5: two failures, three good calls, one failure is not a card."""
    outs = run(ctx_with(tmp_path), "t", [("terminal", FAIL)] * 2 + [("terminal", OK)] * 3 + [("terminal", FAIL)])
    assert cards(outs) == 0


def test_threshold_sets_the_count_and_the_window(tmp_path):
    two = run(ctx_with(tmp_path, autodraw_threshold=2), "t", [("terminal", FAIL), ("terminal", OK), ("terminal", FAIL)])
    assert [o is not None for o in two] == [False, False, True]
    six = run(ctx_with(tmp_path, autodraw_threshold=6), "t",
              [("terminal", FAIL), ("terminal", OK)] + [("terminal", FAIL)] * 5)
    assert [o is not None for o in six].index(True) == 6  # 6 of the last 8


# --- one card per turn (AX-8) ------------------------------------------------------------------------

def test_one_card_per_turn_whatever_the_old_setting_says(tmp_path):
    ctx = ctx_with(tmp_path, autodraw_per_turn=3)
    assert cards(run(ctx, "t", [("terminal", FAIL)] * 9)) == 1
    assert cards(run(ctx, "t2", [("terminal", FAIL)] * 3)) == 1  # a new turn has its own card


def test_settings_have_no_per_turn_and_no_deck_list():
    st = sub("settings")
    assert "autodraw_per_turn" not in st.DEFAULTS
    assert set(st.public(st.read(lambda k, d=None: None))) == {
        "autodraw", "autodraw_threshold", "card_of_day", "learning", "show_in_statusbar", "show_in_sidebar"}
    assert st.SETTABLE == ("autodraw", "autodraw_threshold", "card_of_day", "learning", "show_in_statusbar")


# --- only `auto` cards from decks whose Hermes switch is on (AX-6) ------------------------------------

def test_only_auto_cards_from_hermes_decks(tmp_path):
    ctx = ctx_with(tmp_path)
    store = store_of(ctx)
    decks, journal = sub("decks"), sub("journal")
    mixed = deck_doc("mixed", n=0, prefix="mx", cards=[
        {"id": f"mx-{n:02d}", "human": f"Line {n}.", "agent": f"Do step {n} and report.", "tags": ["auto"] if n < 3 else ["test"]}
        for n in range(1, 9)])
    write_user_deck(store, mixed)
    decks.set_switch(store, "coding", auto=True)  # a deck without auto cards: never a card from it
    decks.set_switch(store, "mixed", auto=True)
    for n in range(40):
        run(ctx, f"t{n}", [("terminal", FAIL)] * 3)
    drawn = {(r["deck"], r["card"]) for r in journal.draws(store, limit=200) if r["by"] == "auto"}
    assert drawn and all(d in ("agent-unblock", "mixed") for d, _ in drawn)
    assert {c for d, c in drawn if d == "mixed"} <= {"mx-01", "mx-02"}
    auto = {c["id"] for c in decks.SHIPPED["agent-unblock"]["cards"] if "auto" in c["tags"]}
    assert {c for d, c in drawn if d == "agent-unblock"} <= auto


def test_hermes_switch_off_means_no_card(tmp_path):
    ctx = ctx_with(tmp_path)
    store = store_of(ctx)
    sub("service").ensure_seed(store, {})
    sub("decks").set_switch(store, "agent-unblock", auto=False)
    assert cards(run(ctx, "t", [("terminal", FAIL)] * 4)) == 0
    rows, _ = store.read_jsonl("journal", sorted(store.listdir("journal"))[-1])
    assert rows[-1]["kind"] == "skipped" and rows[-1]["reason"] == "no_card"


def test_draw_switch_does_not_stop_hermes(tmp_path):
    """The Draw switch is the person's; Hermes reads only its own switch."""
    ctx = ctx_with(tmp_path)
    sub("decks").set_switch(store_of(ctx), "agent-unblock", draw=False)
    assert cards(run(ctx, "t", [("terminal", FAIL)] * 3)) == 1


# --- the one-time seed from a stored autodraw_decks ----------------------------------------------------

def switches(store):
    cat = sub("decks").catalog(store)
    return {slug: d["switch"]["auto"] for slug, d in cat["decks"].items()}


def test_seed_keeps_what_0_1_drew_from(tmp_path):
    decks, service = sub("decks"), sub("service")
    store = make_store(tmp_path)
    decks.set_switch(store, "writing", auto=True)  # 0.1: on, but not in the list: 0.1 never drew from it
    decks.set_switch(store, "design", auto=False)  # 0.1: in the list but switched off
    service.ensure_seed(store, {"autodraw_decks": ["agent-unblock", "coding", "design"]})
    sw = switches(store)
    assert sw["agent-unblock"] and sw["coding"] and not sw["design"] and not sw["writing"] and not sw["shaders"]
    assert decks.read_switches(store)["hermes_seed"]["from"] == ["agent-unblock", "coding", "design"]


def test_seed_runs_once(tmp_path):
    decks, service = sub("decks"), sub("service")
    store = make_store(tmp_path)
    service.ensure_seed(store, {"autodraw_decks": []})
    assert not any(switches(store).values())
    service.ensure_seed(store, {"autodraw_decks": ["agent-unblock", "coding"]})  # a later read changes nothing
    assert not any(switches(store).values())
    decks.set_switch(store, "agent-unblock", auto=True)
    service.ensure_seed(store, {"autodraw_decks": []})
    assert switches(store)["agent-unblock"] is True


def test_seed_without_a_stored_list_is_the_agent_deck_alone(tmp_path):
    store = make_store(tmp_path)
    sub("service").ensure_seed(store, {})
    assert {k for k, v in switches(store).items() if v} == {"agent-unblock"}


def test_seed_follows_an_own_copy_and_new_decks_take_the_defaults(tmp_path):
    decks, service, editor = sub("decks"), sub("service"), sub("editor")
    store = make_store(tmp_path)
    pv = editor.preview(store, "agent-unblock", changes={"remove": ["ag-01"]})
    editor.save(store, "agent-unblock", pv["confirm"], "user", changes={"remove": ["ag-01"]})
    service.ensure_seed(store, {"autodraw_decks": ["agent-unblock"]})
    assert switches(store)["agent-unblock-own"] is True
    write_user_deck(store, deck_doc("later", prefix="lt"))
    assert switches(store)["later"] is False  # a deck made after the seed: Hermes off by default


# --- the matched-tag preference (AX-3, M0 P5) ----------------------------------------------------------

def test_an_unreachable_upstream_brings_a_reframe_card(tmp_path):
    for n in range(12):
        ctx = ctx_with(tmp_path)
        out = run(ctx, "t", [("stamp_lookup", TIMEOUT)] * 3)[2]
        draw_id = json.loads(out)["unblockbruecke_card"]["draw_id"]
        row = next(r for r in sub("journal").draws(store_of(ctx)) if r["draw_id"] == draw_id)
        assert row["card"] in REFRAME, (n, row["card"])


def test_the_match_outlasts_the_repeat_rule(tmp_path):
    """Ten unreachable failures in a row of turns in one profile: every card is a `reframe` card (the
    repeat rule would have left all three out after three draws), and no card comes twice in a row."""
    ctx = ctx_with(tmp_path)
    drawn = []
    for n in range(10):
        run(ctx, f"t{n}", [("stamp_lookup", TIMEOUT)] * 3)
        drawn.append(sub("journal").draws(store_of(ctx))[0]["card"])
    assert set(drawn) <= REFRAME and len(set(drawn)) == 3, drawn
    assert all(a != b for a, b in zip(drawn, drawn[1:])), drawn


def test_a_small_matched_pool_repeats_rather_than_leave_the_match():
    draw = sub("draw")
    deck = {"deck": "d", "cards": [{"id": "dd-01", "tags": ["auto", "reframe"]}, {"id": "dd-02", "tags": ["auto"]},
                                   {"id": "dd-03", "tags": ["auto"]}, {"id": "dd-04", "tags": ["auto"]},
                                   {"id": "dd-05", "tags": ["auto"]}]}
    for seed in range(20):
        got = draw.draw([deck], context="auto", recent={"d": ["dd-01"]}, prefer=["reframe"], rng=__import__("random").Random(seed))
        assert got["card"]["id"] == "dd-01"


def test_other_failures_draw_from_every_auto_card(tmp_path):
    seen = set()
    for n in range(30):
        ctx = ctx_with(tmp_path)
        run(ctx, "t", [("terminal", FAIL)] * 3)
        seen.add(sub("journal").draws(store_of(ctx))[0]["card"])
    assert seen - REFRAME, seen


def test_failure_kind_reads_the_error_text_only_for_the_pick():
    ad = sub("autodraw")
    assert ad.failure_kind(TIMEOUT) == ("unreachable", ("reframe",))
    assert ad.failure_kind(TEXT_FAIL)[0] == "unreachable"
    assert ad.failure_kind(FAIL) == ("", ())
    assert ad.failure_kind(None) == ("", ())


# --- the short payload (AX-7) ---------------------------------------------------------------------------

def test_the_payload_is_the_card_one_sentence_and_the_draw_id(tmp_path):
    ctx = ctx_with(tmp_path)
    out = run(ctx, "t", [("terminal", FAIL)] * 3)[2]
    data = json.loads(out)
    card = data.pop("unblockbruecke_card")
    assert data == json.loads(FAIL)
    assert set(card) == {"card", "note", "draw_id"}
    assert card["note"] == "3 of your last 5 calls failed; this call still failed. A nudge, not an order."
    added = len(out) - len(FAIL)
    assert added <= 360, added  # 585 in 0.1.0; the agent face itself is up to 220
    line = run(ctx_with(tmp_path), "t", [("web_extract", TEXT_FAIL)] * 3)[2]
    assert line.startswith(TEXT_FAIL + "\n\n[unblockbruecke] ") and line.count("\n") == 2
    assert "this call still failed. A nudge, not an order. draw_id " in line


# --- journal rows: where the turn ran, the next call as a fact (AX-2, AX-4) ----------------------------

@pytest.mark.parametrize("surface,where,label", [("desktop", "desktop", "Desktop chat"), ("cli", "cli", "CLI"),
                                                 ("telegram", "messaging", "Telegram chat"), ("", "unknown", "Unknown")])
def test_draw_rows_say_where_the_turn_ran(tmp_path, surface, where, label):
    ctx = ctx_with(tmp_path, surface=surface)
    run(ctx, "t", [("terminal", FAIL)] * 3 + [("read_file", READ_OK)])
    row = sub("journal").draws(store_of(ctx))[0]
    assert (row["where"], row["where_label"]) == (where, label)
    assert row["next_call"] == "ok" and row["next_call_tool"] == "read_file"


def test_next_call_failed_is_a_fact_not_a_verdict(tmp_path):
    ctx = ctx_with(tmp_path)
    run(ctx, "t", [("terminal", FAIL)] * 4)
    row = sub("journal").draws(store_of(ctx))[0]
    assert row["next_call"] == "failed" and "calls_to_recover" not in row["next"]


def test_a_turn_with_no_next_call_has_no_next_call(tmp_path):
    ctx = ctx_with(tmp_path)
    run(ctx, "t", [("terminal", FAIL)] * 3)
    assert "next_call" not in sub("journal").draws(store_of(ctx))[0]


def test_where_reads_cron_kanban_subagent_first(monkeypatch):
    bridge = sub("bridge")

    class Ctx:
        def __init__(self, surface="desktop", cron=None):
            self.surface, self.cron = surface, cron

        def session_surface(self):
            return self.surface

        def current_cron_execution(self):
            return self.cron

    assert bridge.where(Ctx(cron=object())) == ("cron", "")
    monkeypatch.setattr(bridge, "_policy_source", lambda: "kanban")
    assert bridge.where(Ctx(surface="cli")) == ("kanban", "")
    monkeypatch.setattr(bridge, "_policy_source", lambda: "subagent")
    assert bridge.where(Ctx()) == ("subagent", "")
    monkeypatch.setattr(bridge, "_policy_source", lambda: "oneshot")
    assert bridge.where(Ctx(surface="")) == ("cli", "")
    monkeypatch.setattr(bridge, "_policy_source", lambda: "")
    assert bridge.where(Ctx(surface="api_server")) == ("api", "")
    assert bridge.where(Ctx(surface="acp")) == ("editor", "")

    class Broken:
        def session_surface(self):
            raise RuntimeError("moved")

        def current_cron_execution(self):
            raise RuntimeError("moved")

    assert bridge.where(Broken(), environ={})[0] in ("unknown", "cli")


def test_the_agents_own_draw_says_where_too(tmp_path):
    ctx = ctx_with(tmp_path, surface="desktop")
    out = ctx.call("unblockbruecke_card", action="draw", context="stuck")
    row = next(r for r in sub("journal").draws(store_of(ctx)) if r["draw_id"] == out["draw_id"])
    assert row["by"] == "agent" and row["where"] == "desktop"


# --- the routes: GET /settings, POST /setting, GET /journal?by=hermes (contract 0.2 § 2, § 4) ----------

@pytest.fixture
def api(tmp_path):
    mod = sub("api")
    store = make_store(tmp_path)
    saved = {}
    cfg = {"autodraw_decks": ["agent-unblock"]}

    def settings():
        return sub("settings").read(lambda k, d=None: cfg.get(k, d))

    def save(key, value):
        if key == "learning" and value is False and cfg.get("_managed"):
            raise PermissionError("Plugin setting 'plugins.entries.unblockbruecke.settings.learning' is administrator-managed")
        saved[key] = value
        cfg[key] = value

    mod.configure(lambda: store, settings, save, lambda: None)
    mod.saved, mod.cfg, mod.the_store = saved, cfg, store
    yield mod
    mod.configure(None, None)


def test_get_settings_answers_the_contract(api):
    status, body = api.settings_get()
    assert status == 200 and body["ok"] is True
    assert set(body) == {"ok", "schema", "settings", "settable", "ranges", "decks", "hermes"}
    assert "autodraw_decks" not in body["settings"] and "autodraw_per_turn" not in body["settings"]
    assert body["ranges"] == {"autodraw_threshold": [2, 6]}
    row = next(d for d in body["decks"] if d["deck"] == "agent-unblock")
    assert row["name"] == "Agent" and row["mark"] == "robot" and row["switch"] == {"draw": True, "auto": True}
    assert row["auto_cards"] >= 12
    assert all(d["auto_cards"] == 0 for d in body["decks"] if d["deck"] in ("coding", "writing", "design", "shaders"))
    assert body["hermes"]["decks"] == ["agent-unblock"]
    example = body["hermes"]["example"]
    assert example["deck"] == "agent-unblock" and "auto" in example["tags"] and example["face"] == "agent"


@pytest.mark.parametrize("key,value", [("autodraw", True), ("autodraw_threshold", 5), ("card_of_day", False),
                                       ("learning", False), ("show_in_statusbar", False)])
def test_post_setting_saves_one_of_five_keys(api, key, value):
    status, body = api.setting_set({"key": key, "value": value})
    assert status == 200 and body["saved"] == {"key": key, "value": value}
    assert api.saved == {key: value} and body["settings"][key] == value


@pytest.mark.parametrize("key", ["autodraw_decks", "autodraw_per_turn", "show_in_sidebar", "api_key", "", None, 5])
def test_post_setting_refuses_every_other_key(api, key):
    status, body = api.setting_set({"key": key, "value": True})
    assert status == 400 and body["error"] == "unknown_setting" and body["settable"] == list(sub("settings").SETTABLE)
    assert api.saved == {}


@pytest.mark.parametrize("key,value", [("autodraw", "yes"), ("autodraw", 1), ("autodraw_threshold", 7),
                                       ("autodraw_threshold", 1), ("autodraw_threshold", True), ("autodraw_threshold", "3"),
                                       ("learning", None)])
def test_post_setting_refuses_wrong_values(api, key, value):
    status, body = api.setting_set({"key": key, "value": value})
    assert status == 400 and body["error"] == "invalid"
    assert api.saved == {}


def test_post_setting_is_refused_without_a_person(api, tmp_path):
    api.configure(lambda: api.the_store, None, lambda k, v: api.saved.update({k: v}), lambda: "a scheduled job")
    status, body = api.setting_set({"key": "autodraw", "value": True})
    assert status == 403 and body["error"] == "unattended" and api.saved == {}


def test_post_setting_reports_hermes_refusal_and_repeats(api):
    api.cfg["_managed"] = True
    status, body = api.setting_set({"key": "learning", "value": False})
    assert status == 403 and body["error"] == "not_allowed"
    assert api.setting_set({"key": "autodraw", "value": True, "op_id": "op-1"})[0] == 200
    status, body = api.setting_set({"key": "autodraw", "value": False, "op_id": "op-1"})
    assert status == 200 and body["duplicate"] is True and api.saved["autodraw"] is True


def test_route_unattended_reads_the_process_markers():
    bridge = sub("bridge")
    assert bridge.route_unattended({}) is None or bridge.route_unattended({}) == bridge.route_unattended()
    assert bridge.route_unattended({"HERMES_CRON_SESSION": "1"}) == "a scheduled job"
    assert "single-query" in bridge.route_unattended({"HERMES_SINGLE_QUERY_SESSION": "true"})


def test_journal_by_hermes_lists_hermes_draws_with_their_facts(api, tmp_path):
    journal = sub("journal")
    store = api.the_store
    auto = journal.record_draw(store, by="auto", deck="agent-unblock", card="ag-03", face="agent", context="auto",
                               session_id="s", turn_id="t", tool="terminal", streak=3, attached=True, where="kanban")
    journal.record_outcome(store, auto["draw_id"], {"status": "failed", "tool": "terminal"})
    journal.record_draw(store, by="user", deck="coding", card="co-01", face="human", context="any")
    journal.record_draw(store, by="agent", deck="agent-unblock", card="ag-02", face="agent", context="stuck",
                        where="messaging", platform="telegram")
    status, body = api.journal_get(50, "hermes", "")
    assert status == 200 and [d["by"] for d in body["draws"]] == ["agent", "auto"]
    agent, auto_row = body["draws"]
    assert agent["where_label"] == "Telegram chat" and "next_call" not in agent
    assert (auto_row["where"], auto_row["where_label"], auto_row["next_call"], auto_row["next_call_tool"]) == (
        "kanban", "Kanban task", "failed", "terminal")
    assert api.journal_get(50, "robot", "")[0] == 400


def test_user_draws_carry_no_where(api):
    status, body = api.draw({})
    row = sub("journal").draws(api.the_store)[0]
    assert status == 200 and row["by"] == "user" and "where" not in row
