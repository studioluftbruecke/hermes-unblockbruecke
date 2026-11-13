"""Deck files from strangers: a small file must never cost the importing process more than a moment."""
import time

import pytest
from ub_fakes import ROOT, deck_doc, make_store, sub, write_user_deck, yaml_text

editor = sub("editor")
decks = sub("decks")
api = sub("api")


def doubling_aliases(levels: int, where: str = "deck") -> str:
    """A deck file whose `where` value is a list that doubles per alias level (a few hundred bytes)."""
    lines = ["l0: &l0 [ab, ab]"] + [f"l{i}: &l{i} [*l{i - 1}, *l{i - 1}]" for i in range(1, levels + 1)]
    doc = deck_doc("aliased")
    doc.pop(where, None)
    return "\n".join(lines) + f"\n{where}: *l{levels}\n" + yaml_text(doc)


@pytest.mark.parametrize("where", ["deck", "name", "cards"])
def test_an_alias_bomb_is_refused_quickly(tmp_path, where):
    text = doubling_aliases(23, where)
    assert len(text.encode()) < 2000
    started = time.perf_counter()
    with pytest.raises((editor.EditError, decks.DeckError)) as err:
        editor.import_text(make_store(tmp_path), text, "user")
    assert time.perf_counter() - started < 1.0
    assert err.value.code in ("bad_yaml", "invalid_deck")


def test_the_page_import_answers_a_refusal_for_an_alias_bomb(tmp_path):
    api.configure(store_factory=lambda: make_store(tmp_path), settings_factory=lambda: sub("settings").read(lambda k, d=None: d))
    try:
        started = time.perf_counter()
        status, body = api.import_deck({"yaml": doubling_aliases(23)})
        assert time.perf_counter() - started < 1.0
        assert status == 422 and body["ok"] is False
    finally:
        api.configure()


def test_a_deck_name_that_is_not_text_is_a_problem_line(tmp_path):
    doc = deck_doc("listy")
    doc["deck"] = ["listy"]
    with pytest.raises(editor.EditError) as err:
        editor.import_text(make_store(tmp_path), yaml_text(doc), "user")
    assert err.value.code == "invalid_deck"
    assert any(p["rule"] == "slug" for p in err.value.extra["problems"])


def test_a_deck_that_reuses_an_anchor_a_little_still_loads(tmp_path):
    text = "tags: &t [test]\n" + yaml_text(deck_doc("anchored")).replace("tags:\n  - test", "tags: *t")
    doc = decks.parse_yaml(text)
    assert doc["deck"] == "anchored"


def test_an_unknown_top_level_key_is_named_and_the_deck_still_loads():
    deck, problems = decks.validate(deck_doc("extra", glosary={"typo": "A misspelt glossary."}), "extra", file=True)
    assert problems == [] and deck is not None
    assert "glosary" in decks.deck_summary(deck)["warning"]


def test_a_user_deck_with_an_extra_key_keeps_loading_and_the_deck_list_names_the_key(tmp_path):
    store = make_store(tmp_path)
    write_user_deck(store, deck_doc("my-notes", notes="kept for me"))
    write_user_deck(store, deck_doc("plain-deck"))
    cat = decks.catalog(store)
    assert cat["broken"] == {} and {"my-notes", "plain-deck"} <= set(cat["decks"])
    api.configure(store_factory=lambda: store, settings_factory=lambda: sub("settings").read(lambda k, d=None: d))
    try:
        status, body = api.decks_get()
    finally:
        api.configure()
    rows = {r["deck"]: r for r in body["decks"]}
    assert status == 200 and "notes" in rows["my-notes"]["warning"]
    assert "warning" not in rows["plain-deck"] and not any("warning" in r for r in rows.values() if r["source"] == "shipped")


def test_every_key_the_plugin_writes_is_known():
    deck, problems = decks.validate(deck_doc("full", voice="Calm and short.", area="tests"), "full", file=True)
    assert problems == [] and deck is not None and "warning" not in decks.deck_summary(deck)
    written = decks.parse_yaml(decks.dump_yaml(deck))
    again, problems = decks.validate(written, "full", file=True)
    assert problems == [] and "warning" not in decks.deck_summary(again)


def test_an_import_with_an_unknown_key_imports_and_says_the_key_is_not_kept(tmp_path):
    store = make_store(tmp_path)
    out = editor.import_text(store, yaml_text(deck_doc("extra", colour="red")), "user")
    assert out["ok"] is True and "colour" in out["note"]
    assert "warning" not in decks.deck_summary(decks.catalog(store)["decks"]["extra"])
    plain = editor.import_text(store, yaml_text(deck_doc("plain-deck")), "user")
    assert "not kept" not in plain["note"].lower()


def test_check_deck_still_refuses_an_unknown_key_in_a_proposed_deck_file(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("check_deck_unknown_key", ROOT / "scripts" / "check_deck.py")
    assert spec is not None and spec.loader is not None
    check_deck = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(check_deck)
    path = tmp_path / "extra.yaml"
    path.write_text(yaml_text(deck_doc("extra", colour="red")), encoding="utf-8")
    probs = check_deck.check_file(path)
    assert [p["rule"] for p in probs] == ["unknown_key"] and "colour" in probs[0]["message"]
    path.write_text(yaml_text(deck_doc("extra")), encoding="utf-8")
    assert check_deck.check_file(path) == []


@pytest.mark.parametrize("call", ["switch", "deck"])
def test_an_unknown_deck_name_is_echoed_short(tmp_path, call):
    api.configure(store_factory=lambda: make_store(tmp_path), settings_factory=lambda: sub("settings").read(lambda k, d=None: d))
    try:
        name = "x" * 5000
        status, body = api.switch({"deck": name, "draw": True}) if call == "switch" else api.deck_get(name)
        assert status == 404 and len(body["message"]) < 200
    finally:
        api.configure()
