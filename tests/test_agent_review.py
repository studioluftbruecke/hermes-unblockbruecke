"""Review fixes of lane AGENT (v0.1 review): editor, service, auto-draw hook, tools, /card, skill.

Each test names the finding it covers in its docstring and asserts the behaviour the review asked for.
"""
import json
import pathlib
import re

import pytest

from ub_fakes import FakeCtx, deck_doc, load_plugin, make_store, sub, write_user_deck, yaml_text

TERMINAL_FAIL = json.dumps({"output": "Error: boom", "exit_code": 1, "error": "Command failed with exit code 1"})
PLAIN_FAIL = "Error: request timed out"


def tool_ctx(tmp_path, **settings):
    ctx = FakeCtx(tmp_path / "data", settings)
    load_plugin().register(ctx)
    return ctx


def edit(store, slug, changes=None, content=None, author="user"):
    editor = sub("editor")
    pv = editor.preview(store, slug, content, changes)
    assert pv["ok"], pv
    return editor.save(store, slug, pv["confirm"], author, content, changes)


def switch_entry(store, slug):
    return sub("decks").read_switches(store)["decks"].get(slug)


@pytest.fixture
def stand_in_detector():
    """Hermes' verdict for the shapes used here, without Hermes on the path."""
    bridge = sub("bridge")
    bridge.set_detector(lambda tool, result: (isinstance(result, str) and (
        '"exit_code": 1' in result or result.startswith("Error")), ""))
    yield
    bridge.set_detector(None)


def hook_for(tmp_path, settings=None, unattended=None):
    ad = sub("autodraw")
    store = make_store(tmp_path)
    s = sub("settings").read(lambda k, d=None: (settings or {}).get(k, d))
    return ad.AutoDraw(lambda: store, lambda: s, unattended or (lambda: None)), store


def fail_calls(hook, n, turn="t1", session="s1", result=TERMINAL_FAIL, tool="terminal"):
    return [hook(tool_name=tool, result=result, status="error", turn_id=turn, session_id=session) for _ in range(n)]


# --- AGENT-T-export -------------------------------------------------------------------------------

def test_export_never_overwrites_a_file_that_is_not_a_deck(tmp_path):
    """AGENT-T-export: export with overwrite replaced config.yaml and .bashrc with deck YAML."""
    store = make_store(tmp_path)
    editor = sub("editor")
    config = tmp_path / "config.yaml"
    config.write_text("model:\n  default: some-model\n", encoding="utf-8")
    bashrc = tmp_path / ".bashrc"
    bashrc.write_text("export PATH=$PATH:/x\n", encoding="utf-8")
    for target in (config, bashrc):
        before = target.read_text(encoding="utf-8")
        with pytest.raises(editor.EditError):
            editor.export(store, "design", str(target), overwrite=True)
        assert target.read_text(encoding="utf-8") == before
    with pytest.raises(editor.EditError):
        editor.export(store, "design", str(tmp_path / "notes.txt"))
    assert not (tmp_path / "notes.txt").exists()


def test_export_overwrites_an_existing_deck_file_and_writes_yml(tmp_path):
    """AGENT-T-export: a deck file may be replaced; .yml and .yaml names may be written."""
    store = make_store(tmp_path)
    editor = sub("editor")
    old = tmp_path / "design.yaml"
    old.write_text(yaml_text(deck_doc("design", prefix="de")), encoding="utf-8")
    out = editor.export(store, "design", str(old), overwrite=True)
    assert pathlib.Path(out["written"]).read_text(encoding="utf-8") == out["yaml"]
    yml = editor.export(store, "design", str(tmp_path / "copy.yml"))
    assert pathlib.Path(yml["written"]).name == "copy.yml"


def test_agent_export_refusal_is_a_tool_answer(tmp_path):
    """AGENT-T-export through the tool: a refusal, not a write."""
    ctx = tool_ctx(tmp_path)
    target = tmp_path / "config.yaml"
    target.write_text("secret: keep\n", encoding="utf-8")
    out = ctx.call("unblockbruecke_decks", action="export", deck="design", path=str(target), overwrite=True)
    assert out["ok"] is False and out["error"] == "invalid"
    assert target.read_text(encoding="utf-8") == "secret: keep\n"


# --- CORE-5 = UI-03, UI-21: the switch travels with delete, restore and import -----------------------

def test_import_delete_undo_keeps_imported_and_auto_off(tmp_path):
    """CORE-5 / UI-03: import, delete, then the offered undo gave source own with auto-draw on."""
    store = make_store(tmp_path)
    editor, decks = sub("editor"), sub("decks")
    editor.import_text(store, yaml_text(deck_doc("bought", prefix="bo")), "user")
    gone = editor.delete(store, "bought", "user")
    assert "bought" not in decks.catalog(store)["decks"]
    editor.restore(store, "bought", gone["undo"]["restore"], "user")
    deck = decks.catalog(store)["decks"]["bought"]
    assert deck["source"] == "imported" and deck["switch"] == {"draw": True, "auto": False}
    assert decks.drawable(decks.catalog(store), ["bought"], for_auto=True) == []


def test_delete_undo_keeps_an_own_decks_switch(tmp_path):
    """CORE-5: an own deck switched off for drawing comes back switched off."""
    store = make_store(tmp_path)
    editor, decks = sub("editor"), sub("decks")
    edit(store, "mine", {"add": [{"human": "One.", "agent": "Do one thing."}]})
    decks.set_switch(store, "mine", draw=False)
    gone = editor.delete(store, "mine", "user")
    editor.restore(store, "mine", gone["undo"]["restore"], "user")
    deck = decks.catalog(store)["decks"]["mine"]
    assert deck["source"] == "own" and deck["switch"] == {"draw": False, "auto": False}  # 0.2: Hermes off for own decks


def test_a_new_deck_of_a_deleted_name_does_not_inherit_its_switch(tmp_path):
    """CORE-5: delete still forgets the live switch; only the version keeps it."""
    store = make_store(tmp_path)
    editor, decks = sub("editor"), sub("decks")
    editor.import_text(store, yaml_text(deck_doc("bought", prefix="bo")), "user")
    editor.delete(store, "bought", "user")
    assert switch_entry(store, "bought") is None
    edit(store, "bought", {"add": [{"human": "Own now.", "agent": "Do the own thing once."}]})
    assert decks.catalog(store)["decks"]["bought"]["source"] == "own"


def test_import_replace_answers_an_undo_that_restores_text_source_and_switch(tmp_path):
    """UI-21: import with replace over the user's own deck gave no undo and left it imported."""
    store = make_store(tmp_path)
    editor, decks = sub("editor"), sub("decks")
    saved = edit(store, "mine", {"add": [{"human": "Mine.", "agent": "Do my own thing once."}]})
    decks.set_switch(store, "mine", auto=False)
    old_text = editor.current_text(store, "mine")
    out = editor.import_text(store, yaml_text(deck_doc("mine", prefix="mi")), "user", replace=True)
    assert out["undo"] == {"restore": saved["version"]}
    assert decks.catalog(store)["decks"]["mine"]["source"] == "imported"
    back = editor.restore(store, "mine", out["undo"]["restore"], "user")
    assert back["ok"] and editor.current_text(store, "mine") == old_text
    deck = decks.catalog(store)["decks"]["mine"]
    assert deck["source"] == "own" and deck["switch"] == {"draw": True, "auto": False}


def test_import_of_a_new_name_answers_undo_delete(tmp_path):
    """UI-21: the undo has the same shape as a save's undo."""
    store = make_store(tmp_path)
    editor = sub("editor")
    out = editor.import_text(store, yaml_text(deck_doc("bought", prefix="bo")), "user")
    assert out["undo"] == {"delete": "bought"}
    editor.delete(store, "bought", "user")
    again = editor.import_text(store, yaml_text(deck_doc("bought", prefix="bo")), "user")
    assert again["undo"] == {"delete": "bought"}  # the version before is a deletion, not a deck


def test_import_replace_keeps_a_hand_written_deck_as_a_version(tmp_path):
    """UI-21: a deck file with no saved versions is kept first, so the undo has something to restore."""
    store = make_store(tmp_path)
    editor = sub("editor")
    write_user_deck(store, deck_doc("hand", prefix="ha"))
    old_text = editor.current_text(store, "hand")
    out = editor.import_text(store, yaml_text(deck_doc("hand", prefix="hb")), "user", replace=True)
    assert out["undo"] == {"restore": 1}
    editor.restore(store, "hand", 1, "user")
    assert editor.current_text(store, "hand") == old_text


# --- CORE-9: import's and delete's exists checks run inside the store lock ---------------------------

def _interleave(monkeypatch, store, other):
    """Run `other` in a second thread right after the first catalog read of this thread, and give it
    0.5 s to finish. Outside the lock it finishes first; inside the lock it waits for this thread."""
    import threading

    decks = sub("decks")
    real = decks.catalog
    state = {"done": False}
    results = []

    def patched(st):
        cat = real(st)
        if not state["done"]:
            state["done"] = True
            t = threading.Thread(target=lambda: results.append(_try(other)))
            t.start()
            t.join(0.5)
            state["thread"] = t
        return cat

    monkeypatch.setattr(decks, "catalog", patched)
    return state, results


def _try(fn):
    editor = sub("editor")
    try:
        return fn()
    except editor.EditError as exc:
        return {"ok": False, "error": exc.code}


def test_two_imports_of_one_new_name_give_one_deck(tmp_path, monkeypatch):
    """CORE-9: both imports answered ok and the first one survived only as version 1."""
    store = make_store(tmp_path)
    editor = sub("editor")
    text = yaml_text(deck_doc("twin", prefix="tw"))
    state, results = _interleave(monkeypatch, store, lambda: editor.import_text(store, text, "agent"))
    first = _try(lambda: editor.import_text(store, text, "user"))
    state["thread"].join(5)
    answers = [first, *results]
    assert sorted(a.get("error", "ok") for a in answers) == ["exists", "ok"]
    assert len(editor.versions(store, "twin")) == 1


def test_two_deletes_of_one_deck_give_one_deletion(tmp_path, monkeypatch):
    """CORE-9: the same applies to delete."""
    store = make_store(tmp_path)
    editor = sub("editor")
    edit(store, "mine", {"add": [{"human": "One.", "agent": "Do one thing."}]})
    state, results = _interleave(monkeypatch, store, lambda: editor.delete(store, "mine", "agent"))
    first = _try(lambda: editor.delete(store, "mine", "user"))
    state["thread"].join(5)
    assert sorted(a.get("error", "ok") for a in [first, *results]) == ["ok", "unknown_deck"]
    assert sum(1 for v in editor.versions(store, "mine") if v["deleted"]) == 1


# --- CORE-4, UI-05: unknown decks are unknown_deck ---------------------------------------------------

@pytest.mark.parametrize("slug", ["../../../etc", "/etc", "Not A Slug", "x"])
def test_restore_checks_the_slug(tmp_path, slug):
    """CORE-4: restore of a path-like name raised StoreError (route 500) instead of unknown_deck."""
    store = make_store(tmp_path)
    editor = sub("editor")
    with pytest.raises(editor.EditError) as err:
        editor.restore(store, slug, 1, "user")
    assert err.value.code == "unknown_deck"


def test_delete_of_an_unknown_deck_is_unknown_deck(tmp_path):
    """UI-05: delete of a deck that does not exist answered invalid, the contract says unknown_deck."""
    store = make_store(tmp_path)
    editor = sub("editor")
    with pytest.raises(editor.EditError) as err:
        editor.delete(store, "nope", "user")
    assert err.value.code == "unknown_deck"
    with pytest.raises(editor.EditError) as shipped:
        editor.delete(store, "coding", "user")
    assert shipped.value.code == "invalid"
    ctx = tool_ctx(tmp_path)
    assert ctx.call("unblockbruecke_decks", action="delete", deck="nope")["error"] == "unknown_deck"
    assert ctx.call("unblockbruecke_decks", action="restore", deck="../x", version=1)["error"] == "unknown_deck"


# --- CORE-1c, UI-01, AGENT-T-deck-type, -decks-str, -internal, -limit: argument types -----------------

def test_a_string_where_a_list_goes_is_one_name(tmp_path):
    """AGENT-T-decks-str: decks "coding" became the letters c, o, d, i, n, g; tags "bug" found no card."""
    ctx = tool_ctx(tmp_path)
    out = ctx.call("unblockbruecke_card", action="draw", decks="coding")
    assert out["ok"] and out["deck"] == "coding"
    tagged = ctx.call("unblockbruecke_card", action="draw", deck="coding", tags="bug")
    assert tagged["ok"] and "bug" in tagged["card"]["tags"]


@pytest.mark.parametrize("args", [{"deck": 5}, {"deck": ["coding"]}, {"decks": 5}, {"decks": [5]},
                                  {"decks": {"a": 1}}, {"tags": 5}, {"tags": [None]}, {"tags": {"bug": 1}}])
def test_wrong_draw_argument_types_are_invalid(tmp_path, args):
    """AGENT-T-deck-type, AGENT-T-internal: deck 5 drew from every deck; decks 5 or tags 5 answered internal."""
    ctx = tool_ctx(tmp_path)
    out = ctx.call("unblockbruecke_card", action="draw", **args)
    assert out["ok"] is False and out["error"] == "invalid", out


def test_service_refuses_wrong_types_with_value_error(tmp_path):
    """UI-01 (service part): the route maps ValueError to 400 invalid, so the service raises that."""
    store = make_store(tmp_path)
    service = sub("service")
    for kwargs in ({"deck": 5}, {"decks": 5}, {"tags": 5}, {"decks": [["coding"]]}):
        with pytest.raises(ValueError):
            service.draw_card(store, {}, **kwargs)
    assert service.draw_card(store, {}, decks="coding")["card"]["deck"] == "coding"


@pytest.mark.parametrize("limit", [float("inf"), 1e999, -1e999, "many", [3], {"n": 1}, True])
def test_journal_limit_never_internal(tmp_path, limit):
    """AGENT-T-limit: limit 1e999 answered internal OverflowError."""
    ctx = tool_ctx(tmp_path)
    out = ctx.call("unblockbruecke_card", action="journal", limit=limit)
    assert out["ok"] is True


ODD_CHANGES = [
    ["not", "an", "object"], "text", 5,
    {"meta": ["name"]}, {"meta": "name"}, {"meta": {"name": 5}}, {"meta": {"glossary": "x"}},
    {"meta": {"glossary": {"x": 5}}},
    {"remove": 5}, {"remove": {"wr-01": 1}}, {"edit": 5}, {"edit": "wr-01"}, {"add": 5}, {"add": "a card"},
    {"edit": [{"id": "wr-01", "human": 5}]}, {"edit": [{"id": "wr-01", "agent": ["x"]}]},
    {"edit": [{"id": "wr-01", "tags": 5}]}, {"edit": [{"id": "wr-01", "tags": [5]}]},
    {"edit": [{"id": ["wr-01"]}]},
    {"add": [{"human": 5, "agent": "Do it."}]}, {"add": [{"human": "Hi.", "agent": "Do it.", "tags": 5}]},
    {"add": [{"id": 7, "human": "Hi.", "agent": "Do it."}]},
]


@pytest.mark.parametrize("changes", ODD_CHANGES, ids=[str(i) for i in range(len(ODD_CHANGES))])
def test_odd_changes_are_invalid_never_internal(tmp_path, changes):
    """CORE-1c, UI-01: meta as a list, remove as an int, an edit with tags 5 raised TypeError (route 500)."""
    store = make_store(tmp_path)
    editor = sub("editor")
    with pytest.raises((editor.EditError, sub("decks").DeckError)) as err:
        editor.preview(store, "writing", None, changes)
    assert err.value.code in ("invalid", "invalid_deck")
    ctx = tool_ctx(tmp_path)
    out = ctx.call("unblockbruecke_decks", action="preview", deck="writing", changes=changes)
    assert out["ok"] is False and out["error"] in ("invalid", "invalid_deck"), out


def test_a_string_where_a_list_of_changes_goes_is_one_item(tmp_path):
    """CORE-1c: remove "wr-01" is the list ["wr-01"]; an added card's tags "draft" is ["draft"]."""
    store = make_store(tmp_path)
    editor = sub("editor")
    pv = editor.preview(store, "writing", None, {"remove": "wr-01"})
    assert pv["ok"] and [c["id"] for c in pv["diff"]["removed"]] == ["wr-01"]
    pv = editor.preview(store, "writing", None, {"add": [{"human": "Cut one.", "agent": "Cut one sentence and reread.",
                                                          "tags": "draft"}],
                                                 "meta": {"glossary": {"draft": "For a draft."}}})
    assert pv["ok"] and pv["diff"]["added"][0]["tags"] == ["draft"]


def test_show_and_import_refuse_non_text_names(tmp_path):
    """AGENT-T-internal: show with deck or id as a list, import with slug 5, never internal."""
    ctx = tool_ctx(tmp_path)
    for args in ({"deck": ["coding"], "id": "co-01"}, {"deck": "coding", "id": 5}):
        out = ctx.call("unblockbruecke_card", action="show", **args)
        assert out["ok"] is False and out["error"] == "invalid", out
    editor = sub("editor")
    with pytest.raises(editor.EditError) as err:
        editor.import_text(make_store(tmp_path), yaml_text(deck_doc("bought", prefix="bo")), "user", slug=5)
    assert err.value.code == "invalid"


# --- AGENT-T-echo, AGENT-C-echo: unknown names are echoed short ----------------------------------------

def test_unknown_deck_names_are_echoed_short(tmp_path):
    """AGENT-T-echo: a 200000-char deck answered 200138 chars; decks with that string 600136."""
    ctx = tool_ctx(tmp_path)
    long = "x" * 200000
    out = ctx.call("unblockbruecke_card", action="draw", deck=long)
    assert out["error"] == "unknown_deck" and len(out["message"]) < 400
    assert "x" * 40 in out["message"] and "x" * 41 not in out["message"]
    many = [f"nope{i}" for i in range(30)]
    out = ctx.call("unblockbruecke_card", action="draw", decks=many)
    assert "nope4" in out["message"] and "nope5," not in out["message"] and "25 more" in out["message"]
    shown = ctx.call("unblockbruecke_card", action="show", deck=long, id="ag-01")
    assert len(shown["message"]) < 200
    card = ctx.call("unblockbruecke_card", action="show", deck="coding", id="y" * 100000)
    assert len(card["message"]) < 200


def test_card_command_echoes_an_unknown_name_short(tmp_path):
    """AGENT-C-echo: /card <100000 chars> answered 100253 chars."""
    ctx = tool_ctx(tmp_path)
    out = ctx.commands["card"]("x" * 100000)
    assert len(out) < 1000 and "x" * 41 not in out


def test_editor_and_deck_tool_echo_short(tmp_path):
    """AGENT-T-echo: the same cap in the editor (card ids) and unblockbruecke_decks (deck names)."""
    ctx = tool_ctx(tmp_path)
    long = "z" * 5000
    for args in ({"action": "get", "deck": long}, {"action": "switch", "deck": long, "draw": False},
                 {"action": "export", "deck": long}, {"action": "preview", "deck": "writing", "changes": {"remove": [long] * 9}},
                 {"action": "preview", "deck": "writing", "changes": {"edit": [{"id": long}]}}):
        out = ctx.call("unblockbruecke_decks", **args)
        assert out["ok"] is False and len(out["message"]) < 300, (args["action"], len(out["message"]))


# --- CORE-13: an empty autodraw_decks means no auto-draw decks (0.2: through the one-time seed) ---------

def test_empty_autodraw_decks_draws_nothing(tmp_path, stand_in_detector):
    """CORE-13: autodraw_decks [] still auto-drew from agent-unblock. 0.2: a stored [] seeds every Hermes
    switch off once."""
    service, decks = sub("service"), sub("decks")
    store = make_store(tmp_path)
    assert [d["deck"] for d in service.pick_decks(decks.catalog(store), {}, context="auto")] == ["agent-unblock"]
    service.ensure_seed(store, {"autodraw_decks": []})
    assert service.pick_decks(decks.catalog(store), {}, context="auto") == []
    hook, store = hook_for(tmp_path, {"autodraw": True, "autodraw_decks": []})
    assert fail_calls(hook, 3) == [None, None, None]
    rows, _ = store.read_jsonl("journal", "2026-11.jsonl")
    assert rows[-1]["kind"] == "skipped" and rows[-1]["reason"] == "no_card"
    default, _ = hook_for(tmp_path / "b", {"autodraw": True})
    assert fail_calls(default, 3)[2] is not None


# --- AGENT-U-cron: the cron surface is unattended ------------------------------------------------------

class CronCtx:
    def __init__(self, surface, cron):
        self.surface, self.cron = surface, cron

    def session_surface(self):
        return self.surface

    def current_cron_execution(self):
        if isinstance(self.cron, Exception):
            raise self.cron
        return self.cron


BOOM = RuntimeError("ctx call failed over the host wire")


@pytest.mark.parametrize("environ", [{"HERMES_PLUGIN_HOST_PROCESS": "1"}, {}], ids=["host", "in_process"])
def test_cron_surface_is_unattended_when_the_cron_call_fails(environ):
    """AGENT-U-cron: surface cron with current_cron_execution() raising counted as attended."""
    bridge = sub("bridge")
    assert bridge.unattended_reason(CronCtx("cron", BOOM), environ=environ) is not None
    assert bridge.unattended_reason(CronCtx("cron", None), environ=environ) is not None


def test_host_mode_counts_a_raising_cron_call_as_unattended():
    """AGENT-U-cron: in host mode a raising current_cron_execution() fails closed on any surface."""
    bridge = sub("bridge")
    assert bridge.unattended_reason(CronCtx("desktop", BOOM), environ={"HERMES_PLUGIN_HOST_PROCESS": "1"})
    assert bridge.unattended_reason(CronCtx("desktop", None), environ={"HERMES_PLUGIN_HOST_PROCESS": "1"}) is None
    assert bridge.unattended_reason(CronCtx("desktop", BOOM), environ={}) is None  # in-process: the env markers decide


# --- AGENT-H-session: no turn_id, no auto-draw ----------------------------------------------------------

def test_no_turn_id_means_no_auto_draw(tmp_path, stand_in_detector):
    """AGENT-H-session: with turn_id empty the session_id was the key, so after one card that session
    never got another. Auto-draw now counts per turn only and skips calls without a turn_id."""
    hook, store = hook_for(tmp_path, {"autodraw": True})
    out = fail_calls(hook, 6, turn="", session="only-session")
    assert out == [None] * 6
    assert store.listdir("journal") == []
    assert fail_calls(hook, 3, turn="t-real", session="only-session")[2] is not None


# --- AGENT-H-rate: an auto-drawn card can be rated ------------------------------------------------------

def test_auto_card_carries_its_draw_id_in_json(tmp_path, stand_in_detector):
    """AGENT-H-rate: the auto card payload had no draw_id, so the agent could not rate it."""
    ctx = tool_ctx(tmp_path, autodraw=True)
    hook = ctx.hooks["transform_tool_result"]
    out = fail_calls(hook, 3)[2]
    payload = json.loads(out)["unblockbruecke_card"]
    row = sub("journal").draws(sub("store").Store(tmp_path / "data"))[0]
    assert payload["draw_id"] == row["draw_id"] and row["by"] == "auto" and row["attached"] is True
    rated = ctx.call("unblockbruecke_card", action="rate", draw_id=payload["draw_id"], rating="helped")
    assert rated["ok"] and rated["rated"]["draw_id"] == payload["draw_id"]


def test_auto_card_carries_its_draw_id_in_plain_text(tmp_path, stand_in_detector):
    """AGENT-H-rate: the plain-text line names the draw_id too."""
    hook, store = hook_for(tmp_path, {"autodraw": True})
    out = fail_calls(hook, 3, result=PLAIN_FAIL, tool="web_extract")[2]
    line = out.split("\n\n")[-1]
    row = sub("journal").draws(store)[0]
    assert line.startswith("[unblockbruecke]") and f"draw_id {row['draw_id']}" in line


def test_a_shape_that_takes_no_card_is_journaled_as_not_offered(tmp_path, stand_in_detector):
    """AGENT-H-rate / AGENT-H-attached: a result shape that takes no card leaves the result alone and
    the journal row says attached false."""
    hook, store = hook_for(tmp_path, {"autodraw": True})
    sub("bridge").set_detector(lambda tool, result: (True, ""))
    out = fail_calls(hook, 3, result=json.dumps([{"error": "x"}]))
    assert out == [None, None, None]
    row = sub("journal").draws(store)[0]
    assert row["attached"] is False


# --- AGENT-H-cost: auto-draw off reads one setting ------------------------------------------------------

class CountingCtx(FakeCtx):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.reads = []

    def get_config(self, key, default=None):
        self.reads.append(key)
        return super().get_config(key, default)


def test_autodraw_off_reads_only_the_autodraw_setting(tmp_path, stand_in_detector):
    """AGENT-H-cost: every tool call read all 7 settings before checking autodraw (7 IPC round trips
    per call under plugins.isolation: host)."""
    ctx = CountingCtx(tmp_path / "data")
    load_plugin().register(ctx)
    hook = ctx.hooks["transform_tool_result"]
    assert hook(tool_name="terminal", result=TERMINAL_FAIL, status="error", turn_id="t1", session_id="s1") is None
    assert ctx.reads == ["autodraw"]
    ctx.settings["autodraw"] = True
    ctx.reads.clear()
    fail_calls(hook, 3)
    assert "autodraw_threshold" in ctx.reads  # on: the rest is read as before


# --- AGENT-D-catalog, AGENT-D-copy: descriptions lead with their actions ---------------------------------

CATALOG = 78  # characters of a description the deferred-tool catalog shows


@pytest.mark.parametrize("tool", ["unblockbruecke_card", "unblockbruecke_decks"])
def test_every_action_is_in_the_catalog_head(tmp_path, tool):
    """AGENT-D-catalog: 0/5 and 0/10 actions were inside the first 78 characters."""
    ctx = tool_ctx(tmp_path)
    reg = ctx.tools[tool]
    head = reg["description"][:CATALOG]
    actions = reg["schema"]["parameters"]["properties"]["action"]["enum"]
    assert [a for a in actions if not re.search(rf"\b{a}\b", head)] == []


@pytest.mark.parametrize("tool", ["unblockbruecke_card", "unblockbruecke_decks"])
def test_no_description_sentence_over_160_characters(tmp_path, tool):
    """AGENT-D-copy: sentences of 239 (card) and 555 (decks) characters."""
    ctx = tool_ctx(tmp_path)
    desc = ctx.tools[tool]["description"]
    assert [s for s in re.split(r"(?<=[.!?])\s+", desc) if len(s) > 160] == []
    assert len(desc) < 800


def test_the_change_format_moved_to_the_parameter_and_the_rules_to_the_refusal(tmp_path):
    """AGENT-D-copy: the change format lives in the changes parameter, not the description. 0.2 (AX-9):
    the card rules left the skill, so a refused preview must name the rule the card broke."""
    ctx = tool_ctx(tmp_path)
    schema = ctx.tools["unblockbruecke_decks"]["schema"]
    assert "edit: [{id" in schema["parameters"]["properties"]["changes"]["description"]
    out = ctx.call("unblockbruecke_decks", action="preview", deck="writing",
                   changes={"add": [{"human": "x" * 120, "agent": "Do one small thing.", "tags": ["auto"]}]})
    assert out["ok"] is False and "at most 90" in out["message"] and out["problems"][0]["rule"] == "length_human"


# --- AGENT-S-plain, AGENT-S-threshold: the skill describes auto-draw as it works ---------------------------

def skill_text():
    return (pathlib.Path(sub("decks").PLUGIN_ROOT) / "skills" / "unblockbruecke" / "SKILL.md").read_text(encoding="utf-8")


def test_skill_names_both_card_shapes():
    """AGENT-S-plain: the skill said the card always arrives under the key unblockbruecke_card."""
    text = skill_text()
    assert "`unblockbruecke_card`" in text and "[unblockbruecke]" in text and "draw_id" in text


def test_skill_says_the_threshold_is_a_setting():
    """AGENT-S-threshold: the skill hard-coded three failed calls."""
    text = skill_text()
    assert "three failed tool calls" not in text.lower() and "third failing" not in text.lower()
    assert "autodraw_threshold" in text and "default 3" in text


# --- the same fixes seen through the dashboard routes (api.py, no FastAPI) --------------------------------

@pytest.fixture
def api(tmp_path):
    mod = sub("api")
    store = make_store(tmp_path)
    settings = sub("settings").read(lambda k, d=None: None)
    mod.configure(lambda: store, lambda: settings)
    yield mod
    mod.configure(None, None)


def test_routes_answer_the_contract_codes(api):
    """UI-01, UI-05, CORE-4, UI-21 at the route: 400 invalid, 404 unknown_deck, an undo on import."""
    for body in ({"decks": 5}, {"deck": ["coding"]}, {"decks": [5]}):
        status, out = api.draw(body)
        assert status == 400 and out["error"] == "invalid", (body, status, out)
    for changes in ({"remove": 5}, {"meta": ["name"]}, {"edit": [{"id": "wr-01", "tags": 5}]}):
        status, out = api.preview("writing", {"changes": changes})
        assert status == 400 and out["error"] == "invalid", (changes, status, out)
    assert api.delete("nope", {})[0] == 404
    assert api.restore("..", {"version": 1})[0] == 404
    status, out = api.import_deck({"yaml": yaml_text(deck_doc("bought", prefix="bo"))})
    assert status == 200 and out["undo"] == {"delete": "bought"}
