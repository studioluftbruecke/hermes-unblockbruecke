"""Names and ids are checked whole: a trailing line break is not part of any valid name."""
import pytest
from ub_fakes import card, deck_doc, make_store, sub, yaml_text

decks = sub("decks")
editor = sub("editor")
store_mod = sub("store")
api = sub("api")


def test_a_card_id_with_a_trailing_newline_is_a_problem_line():
    deck, problems = decks.validate(deck_doc("tidy", cards=[card(1, "ab"), {**card(2, "ab"), "id": "ab-02\n"}]), "tidy")
    assert deck is None
    assert any(p["card"] == "ab-02\n" or "ab-02" in str(p) for p in problems)


def test_a_tag_with_a_trailing_newline_is_a_problem_line():
    deck, problems = decks.validate(deck_doc("tidy", cards=[card(1, "ab", tags=["test\n"])]), "tidy")
    assert deck is None and problems


def test_an_import_under_a_name_with_a_trailing_newline_is_refused(tmp_path):
    s = make_store(tmp_path)
    with pytest.raises((editor.EditError, decks.DeckError)):
        editor.import_text(s, yaml_text(deck_doc("mine")), "user", slug="mine\n")
    assert not list((tmp_path / "data").rglob("mine\n.yaml"))


def test_a_deck_file_naming_itself_with_a_trailing_newline_is_refused(tmp_path):
    with pytest.raises((editor.EditError, decks.DeckError)):
        editor.import_text(make_store(tmp_path), yaml_text(deck_doc("mine\n")), "user")


def test_the_store_refuses_a_path_part_with_a_trailing_newline():
    with pytest.raises(store_mod.StoreError):
        store_mod.check_slug("week\n")


def test_an_op_id_with_a_trailing_newline_is_refused(tmp_path):
    api.configure(store_factory=lambda: make_store(tmp_path), settings_factory=lambda: sub("settings").read(lambda k, d=None: d))
    try:
        status, body = api.import_deck({"yaml": yaml_text(deck_doc("opdeck")), "op_id": "op-1\n"})
        assert status == 400 and body["ok"] is False
    finally:
        api.configure()
