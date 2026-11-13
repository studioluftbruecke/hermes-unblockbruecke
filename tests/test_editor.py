"""M4: the deck editor (preview, save, versions, restore, delete, import, export), switches, the agent's
`unblockbruecke_decks`, and `check_deck.py` against the bad fixtures."""
import importlib.util
import json
import pathlib

import pytest

from ub_fakes import FakeCtx, card, deck_doc, load_plugin, make_store, sub, write_user_deck, yaml_text

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "bad"


def edit(store, slug, changes=None, content=None, author="user"):
    editor = sub("editor")
    pv = editor.preview(store, slug, content, changes)
    assert pv["ok"], pv
    return pv, editor.save(store, slug, pv["confirm"], author, content, changes)


def test_editing_a_shipped_deck_saves_an_own_copy_that_replaces_it(tmp_path):
    store = make_store(tmp_path)
    decks = sub("decks")
    pv, saved = edit(store, "coding", {"add": [{"human": "Rename it out loud.", "agent": "Say the new name to the user and wait for a nod.",
                                                "tags": ["naming"]}]})
    assert pv["target"] == "coding-own" and pv["copy_of"] == "coding"
    assert pv["diff"]["added"][0]["id"] == "co-09" and pv["summary"] == "own copy of coding: 1 card added"
    assert saved["deck"] == "coding-own" and saved["version"] == 1 and saved["undo"] == {"delete": "coding-own"}
    cat = decks.catalog(store)
    assert cat["decks"]["coding"]["shadowed_by"] == "coding-own"
    assert len(decks.resolve(cat, "coding")["cards"]) == 9
    assert (pathlib.Path(decks.SHIPPED_DIR) / "coding.yaml").read_text(encoding="utf-8").count("co-09") == 0


def test_a_new_deck_is_drawable_at_once_and_versions_restore(tmp_path):
    store = make_store(tmp_path)
    editor, service = sub("editor"), sub("service")
    _, first = edit(store, "my-music", {"meta": {"name": "My music"},
                                        "add": [{"human": "Mute the loudest track.", "agent": "Ask which track is loudest, then suggest muting it for one pass."},
                                                {"human": "Half the tempo.", "agent": "Suggest playing the section at half tempo once and noting what changes."}]})
    assert first["version"] == 1
    drawn = service.draw_card(store, {}, deck="my-music")
    assert drawn["card"]["deck"] == "my-music" and drawn["card"]["id"] in ("my-01", "my-02")
    _, second = edit(store, "my-music", {"edit": [{"id": "my-01", "human": "Mute the track you love."}], "remove": ["my-02"]},
                     author="agent")
    assert second["version"] == 2 and second["summary"] == "1 card changed; 1 card removed"
    assert second["undo"] == {"restore": 1}
    vs = editor.versions(store, "my-music")
    assert [(v["n"], v["author"]) for v in vs] == [(2, "agent"), (1, "user")]
    back = editor.restore(store, "my-music", 1, "user")
    assert back["version"] == 3 and back["summary"] == "1 card added; 1 card changed"
    deck = sub("decks").catalog(store)["decks"]["my-music"]
    assert [c["human"] for c in deck["cards"]] == ["Mute the loudest track.", "Half the tempo."]


def test_confirm_ignores_key_order(tmp_path):
    """Found live (M4): the model sent the same deck with its keys sorted, and save answered stale_preview."""
    store = make_store(tmp_path)
    editor = sub("editor")
    content = {"name": "Mine", "glossary": {"music": "Music work.", "constraint": "Removes an option."},
               "cards": [{"id": "mi-01", "human": "One.", "agent": "Do one thing.", "tags": ["music", "constraint"]}]}
    pv = editor.preview(store, "mine", content)
    assert pv["ok"], pv
    resorted = {"cards": [{"agent": "Do one thing.", "human": "One.", "id": "mi-01", "tags": ["music", "constraint"]}],
                "glossary": {"constraint": "Removes an option.", "music": "Music work."}, "name": "Mine"}
    assert editor.save(store, "mine", pv["confirm"], "agent", resorted)["version"] == 1


def test_a_new_tag_from_the_page_gets_a_plain_glossary_line(tmp_path):
    """Found in the step-7 dry read: the page has no glossary field, so a new tag could never save."""
    store = make_store(tmp_path)
    editor = sub("editor")
    pv, saved = edit(store, "my-test", {"add": [{"human": "Hum it.", "agent": "Ask for the hook, hummed once.",
                                                 "tags": ["music"]}]})
    assert pv["ok"] and saved["version"] == 1
    deck = sub("decks").catalog(store)["decks"]["my-test"]
    assert deck["glossary"]["music"] == editor.ADDED_TAG
    own = {"edit": [{"id": "co-01", "tags": ["naming", "sketch"]}]}
    pv = editor.preview(store, "coding", changes=own)
    assert pv["ok"], pv
    whole = editor.preview(store, "strict", {"name": "Strict", "cards": [
        {"id": "st-01", "human": "One.", "agent": "Do one thing.", "tags": ["nope"]}]})
    assert whole["ok"] is False


def test_save_refuses_a_stale_or_different_preview(tmp_path):
    store = make_store(tmp_path)
    editor = sub("editor")
    edit(store, "mine", {"add": [{"human": "One.", "agent": "Do one thing."}]})
    pv = editor.preview(store, "mine", changes={"add": [{"human": "Two.", "agent": "Do two things."}]})
    edit(store, "mine", {"add": [{"human": "Other.", "agent": "Do another thing."}]})  # someone saved meanwhile
    with pytest.raises(editor.EditError) as err:
        editor.save(store, "mine", pv["confirm"], "agent", changes={"add": [{"human": "Two.", "agent": "Do two things."}]})
    assert err.value.code == "stale_preview"
    pv2 = editor.preview(store, "mine", changes={"add": [{"human": "Two.", "agent": "Do two things."}]})
    with pytest.raises(editor.EditError):
        editor.save(store, "mine", pv2["confirm"], "agent", changes={"add": [{"human": "Three.", "agent": "Sneak in."}]})


def test_preview_names_the_rule_a_card_breaks(tmp_path):
    store = make_store(tmp_path)
    out = sub("editor").preview(store, "mine", changes={"add": [{"human": "Go to www.example.com", "agent": "Run `rm -rf`."}]})
    assert out["ok"] is False and {p["rule"] for p in out["problems"]} >= {"url", "code", "shell"}


def test_versions_keep_the_last_twenty(tmp_path):
    store = make_store(tmp_path)
    editor = sub("editor")
    for i in range(25):
        edit(store, "mine", {"add": [{"human": f"Card {i}.", "agent": f"Do step {i}."}]})
    vs = editor.versions(store, "mine")
    assert len(vs) == 20 and vs[0]["n"] == 25 and vs[-1]["n"] == 6
    assert sorted(store.listdir("decks.versions", "mine")) == sorted([f"{n}.yaml" for n in range(6, 26)] + ["index.json"])
    with pytest.raises(editor.EditError):
        editor.restore(store, "mine", 2, "user")


def test_delete_own_deck_and_bring_it_back(tmp_path):
    store = make_store(tmp_path)
    editor, decks = sub("editor"), sub("decks")
    edit(store, "mine", {"add": [{"human": "One.", "agent": "Do one thing."}]})
    gone = editor.delete(store, "mine", "user")
    assert "mine" not in decks.catalog(store)["decks"] and gone["undo"] == {"restore": 2}
    editor.restore(store, "mine", gone["undo"]["restore"], "user")
    assert "mine" in decks.catalog(store)["decks"]
    with pytest.raises(editor.EditError):
        editor.delete(store, "coding", "user")


def test_import_marks_the_deck_imported_and_off_for_auto(tmp_path):
    store = make_store(tmp_path)
    editor, decks = sub("editor"), sub("decks")
    src = tmp_path / "bought.yaml"
    src.write_text(yaml_text(deck_doc("bought", prefix="bo")), encoding="utf-8")
    out = editor.import_file(store, str(src), "user")
    assert out["source"] == "imported" and out["cards"] == 5
    deck = decks.catalog(store)["decks"]["bought"]
    assert deck["source"] == "imported" and deck["switch"] == {"draw": True, "auto": False}
    with pytest.raises(editor.EditError) as again:
        editor.import_file(store, str(src), "user")
    assert again.value.code == "exists"
    shipped_name = tmp_path / "coding.yaml"
    shipped_name.write_text(yaml_text(deck_doc("coding", prefix="co")), encoding="utf-8")
    with pytest.raises(editor.EditError):
        editor.import_file(store, str(shipped_name), "user")
    renamed = editor.import_file(store, str(shipped_name), "user", slug="coding-friend")
    assert renamed["deck"] == "coding-friend"
    with pytest.raises(editor.EditError):
        editor.import_file(store, "relative.yaml", "user")
    bad = FIXTURES / "url.yaml"
    with pytest.raises(editor.EditError) as invalid:
        editor.import_file(store, str(bad), "user")
    assert invalid.value.code == "invalid_deck" and "(url)" in str(invalid.value)


def test_export_text_and_file(tmp_path):
    store = make_store(tmp_path)
    editor, decks = sub("editor"), sub("decks")
    out = editor.export(store, "design")
    assert out["file_name"] == "design.yaml" and decks.load_text(out["yaml"], "design")["cards"]
    target = tmp_path / "out"
    target.mkdir()
    written = editor.export(store, "design", str(target))
    assert pathlib.Path(written["written"]).read_text(encoding="utf-8") == out["yaml"]
    with pytest.raises(editor.EditError):
        editor.export(store, "design", str(target))
    assert editor.export(store, "design", str(target), overwrite=True)["written"]


# --- the agent tool -------------------------------------------------------------------------------

def tool_ctx(tmp_path):
    ctx = FakeCtx(tmp_path / "data")
    load_plugin().register(ctx)
    return ctx


def test_agent_previews_saves_and_undoes(tmp_path):
    ctx = tool_ctx(tmp_path)
    change = {"add": [{"human": "Read it backwards.", "agent": "Read the last paragraph first and say what it promises.",
                       "tags": ["draft"]}], "meta": {"glossary": {"draft": "For a draft that will not move."}}}
    pv = ctx.call("unblockbruecke_decks", action="preview", deck="writing", changes=change)
    assert pv["ok"] and pv["target"] == "writing-own" and "yaml" not in pv and pv["next"].startswith("Show the user")
    bad = ctx.call("unblockbruecke_decks", action="save", deck="writing", changes=change, confirm="nope")
    assert bad["error"] == "stale_preview" and bad["preview"]["confirm"] == pv["confirm"]
    saved = ctx.call("unblockbruecke_decks", action="save", deck="writing", changes=change, confirm=pv["confirm"])
    assert saved["ok"] and saved["deck"] == "writing-own" and saved["version"] == 1
    got = ctx.call("unblockbruecke_decks", action="get", deck="writing-own")
    assert got["deck"]["editable"] and len(got["deck"]["cards"]) == 17
    versions = ctx.call("unblockbruecke_decks", action="versions", deck="writing-own")
    assert versions["versions"][0]["author"] == "agent"
    deleted = ctx.call("unblockbruecke_decks", action="delete", deck="writing-own")
    assert deleted["ok"] and ctx.call("unblockbruecke_card", action="draw", deck="writing")["deck"] == "writing"


def test_agent_switch_and_list(tmp_path):
    ctx = tool_ctx(tmp_path)
    out = ctx.call("unblockbruecke_decks", action="switch", deck="shaders", draw=False)
    assert out["switch"] == {"draw": False, "auto": False}  # 0.2: Hermes draws from the Agent deck alone
    listed = {d["deck"]: d for d in ctx.call("unblockbruecke_decks", action="list")["decks"]}
    assert listed["shaders"]["switch"]["draw"] is False
    assert ctx.call("unblockbruecke_decks", action="switch", deck="nope", draw=True)["error"] == "unknown_deck"


def test_agent_writes_refused_unattended(tmp_path, monkeypatch):
    ctx = tool_ctx(tmp_path)
    monkeypatch.setattr(sub("bridge"), "_finite_turn", lambda: True)
    for action, extra in (("save", {"deck": "x", "confirm": "y"}), ("restore", {"deck": "x", "version": 1}),
                          ("delete", {"deck": "x"}), ("switch", {"deck": "coding", "draw": False}),
                          ("import", {"path": "/tmp/x.yaml"}), ("export", {"deck": "coding", "path": str(tmp_path)})):
        out = ctx.call("unblockbruecke_decks", action=action, **extra)
        assert out["error"] == "unattended" and "Nothing was changed" in out["message"], action
    assert ctx.call("unblockbruecke_decks", action="list")["ok"]
    assert ctx.call("unblockbruecke_decks", action="preview", deck="mine",
                    changes={"add": [{"human": "a", "agent": "b"}]})["ok"]
    assert ctx.call("unblockbruecke_decks", action="export", deck="coding")["ok"]
    assert not list(tmp_path.glob("*.yaml"))


# --- check_deck.py on the bad fixtures (F14) ------------------------------------------------------

@pytest.mark.parametrize("name,rule", [("html", "html"), ("url", "url"), ("too-long", "length_human"),
                                       ("duplicate-id", "id"), ("missing-face", "length_agent")])
def test_check_deck_refuses_each_bad_fixture_with_its_rule(name, rule):
    script = pathlib.Path(sub("decks").__file__).resolve().parent / "scripts" / "check_deck.py"
    spec = importlib.util.spec_from_file_location("check_deck_m4", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    probs = mod.check_file(FIXTURES / f"{name}.yaml")
    assert rule in {p["rule"] for p in probs}, probs
