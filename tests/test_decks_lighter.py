"""Lighter deck edits, the engine: a person's edit of an own deck saves at once with one
request and is undone with one; tags are optional in the user's decks and still required in shipped and
community deck files (`scripts/check_deck.py`). Red on 0.1.0 and 0.1.4: a save without `confirm` was a
409 `stale_preview`, and a card without tags was refused everywhere.
"""
import importlib.util

import pytest

from ub_fakes import ROOT, card, deck_doc, make_store, sub, write_user_deck, yaml_text


@pytest.fixture
def api(tmp_path):
    mod = sub("api")
    store = make_store(tmp_path)
    settings = sub("settings").read(lambda k, d=None: None)
    mod.configure(lambda: store, lambda: settings)
    mod.the_store = store
    yield mod
    mod.configure(None, None)


def cards_of(api, slug):
    status, body = api.deck_get(slug)
    assert status == 200, body
    return [c["id"] for c in body["deck"]["cards"]]


def test_adding_a_card_to_an_own_deck_is_one_request_and_one_undo(api):
    write_user_deck(api.the_store, deck_doc("mine", prefix="mi", n=2))
    before = cards_of(api, "mine")
    status, out = api.save("mine", {"changes": {"add": [{"human": "Walk round the block.", "agent": "Stop and list what you know."}]}})
    assert status == 200 and out["saved_at_once"] is True and out["deck"] == "mine"
    added = [c["id"] for c in out["diff"]["added"]]
    assert cards_of(api, "mine") == before + added and len(added) == 1
    assert set(out["undo"]) == {"restore"}
    status, back = api.restore("mine", {"version": out["undo"]["restore"]})
    assert status == 200 and cards_of(api, "mine") == before
    assert back["undo"] == {"restore": back["version"] - 1}  # the undo of the undo


def test_a_new_deck_saves_at_once_and_its_undo_deletes_it(api):
    status, out = api.save("my-ideas", {"changes": {"meta": {"name": "My ideas"},
                                                    "add": [{"human": "Say it badly first.", "agent": "Write the rough version."}]}})
    assert status == 200 and out["saved_at_once"] is True and out["undo"] == {"delete": "my-ideas"}
    status, deck = api.deck_get("my-ideas")
    assert deck["deck"]["name"] == "My ideas" and deck["deck"]["cards"][0]["tags"] == []  # no tag needed
    assert deck["deck"]["saves_at_once"] is True
    status, gone = api.delete("my-ideas", {})
    assert status == 200 and api.deck_get("my-ideas")[0] == 404


def test_an_existing_own_copy_saves_at_once(api):
    editor = sub("editor")
    pv = editor.preview(api.the_store, "coding", changes={"remove": ["co-01"]})
    editor.save(api.the_store, "coding", pv["confirm"], "user", changes={"remove": ["co-01"]})
    status, out = api.save("coding", {"changes": {"remove": ["co-02"]}})
    assert status == 200 and out["deck"] == "coding-own" and out["saved_at_once"] is True


@pytest.mark.parametrize("slug", ["coding", "agent-unblock"])
def test_the_first_own_copy_of_a_shipped_deck_keeps_the_preview(api, slug):
    status, out = api.save(slug, {"changes": {"remove": [cards_of(api, slug)[0]]}})
    assert status == 409 and out["error"] == "stale_preview" and out["preview"]["target"] == f"{slug}-own"
    assert api.deck_get(slug)[1]["deck"]["saves_at_once"] is False
    status, saved = api.save(slug, {"changes": {"remove": [cards_of(api, slug)[0]]}, "confirm": out["preview"]["confirm"]})
    assert status == 200 and saved["saved_at_once"] is False


def test_an_imported_deck_keeps_the_preview(api):
    api.import_deck({"yaml": yaml_text(deck_doc("bought", prefix="bo"))})
    status, out = api.save("bought", {"changes": {"remove": ["bo-01"]}})
    assert status == 409 and out["error"] == "stale_preview"


def test_a_stale_confirm_is_still_refused_on_an_own_deck(api):
    write_user_deck(api.the_store, deck_doc("mine", prefix="mi", n=2))
    status, out = api.save("mine", {"changes": {"remove": ["mi-01"]}, "confirm": "not-the-preview"})
    assert status == 409 and out["error"] == "stale_preview" and cards_of(api, "mine") == ["mi-01", "mi-02"]


def test_the_agent_keeps_the_preview_on_its_own_decks(tmp_path):
    from ub_fakes import FakeCtx, load_plugin

    ctx = FakeCtx(tmp_path / "data")
    load_plugin().register(ctx)
    write_user_deck(load_plugin().make_store(ctx), deck_doc("mine", prefix="mi", n=2))
    out = ctx.call("unblockbruecke_decks", action="save", deck="mine", changes={"remove": ["mi-01"]})
    assert out["ok"] is False and out["error"] == "stale_preview"


def test_a_card_without_tags_loads_in_an_own_deck(tmp_path):
    decks = sub("decks")
    store = make_store(tmp_path)
    write_user_deck(store, deck_doc("bare", prefix="ba", cards=[{"id": "ba-01", "human": "Look up.", "agent": "Read the error.", "tags": []},
                                                                {"id": "ba-02", "human": "Look down.", "agent": "Read the log."}]))
    cat = decks.catalog(store)
    assert "bare" in cat["decks"] and "bare" not in cat["broken"]
    assert [c["tags"] for c in cat["decks"]["bare"]["cards"]] == [[], []]
    out = sub("service").draw_card(store, {}, deck="bare")
    assert out["card"]["tags"] == [] and out["card"]["why"] == []


def test_an_imported_file_without_tags_loads(api):
    doc = deck_doc("loose", prefix="lo", cards=[{"id": "lo-01", "human": "Breathe.", "agent": "Re-read the task."}])
    status, out = api.import_deck({"yaml": yaml_text(doc)})
    assert status == 200 and out["cards"] == 1


def check_deck():
    spec = importlib.util.spec_from_file_location("ub_check_deck_test", ROOT / "scripts" / "check_deck.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_a_card_without_tags_is_still_refused_in_a_community_deck_file(tmp_path):
    for n, cards in enumerate(([{"id": "cm-01", "human": "Pause.", "agent": "Stop and re-read the goal.", "tags": []}],
                               [{"id": "cm-01", "human": "Pause.", "agent": "Stop and re-read the goal."}])):
        path = tmp_path / f"community-{n}.yaml"
        path.write_text(yaml_text(deck_doc(f"community-{n}", prefix="cm", cards=cards)), encoding="utf-8")
        probs = check_deck().check_file(path)
        assert [p["rule"] for p in probs] == ["tags"] and "1 to 4 tags" in probs[0]["message"], probs
    ok = tmp_path / "community-ok.yaml"
    ok.write_text(yaml_text(deck_doc("community-ok", prefix="cm", cards=[card(1, "cm")])), encoding="utf-8")
    assert check_deck().check_file(ok) == []


def test_the_shipped_loader_still_needs_tags():
    decks = sub("decks")
    doc = deck_doc("ship-x", prefix="sx", cards=[{"id": "sx-01", "human": "Pause.", "agent": "Stop.", "tags": []}])
    with pytest.raises(decks.DeckError) as exc:
        decks.load_text(yaml_text(doc), "ship-x")
    assert exc.value.problems[0]["rule"] == "tags"


def test_more_than_four_tags_are_still_refused_in_an_own_deck(api):
    status, out = api.save("many", {"changes": {"add": [{"human": "a", "agent": "b", "tags": ["t1x", "t2x", "t3x", "t4x", "t5x"]}]}})
    assert status == 422 and out["error"] == "invalid_deck" and out["problems"][0]["rule"] == "tags"
    assert out["problems"][0]["message"] == "a card has at most 4 tags"
