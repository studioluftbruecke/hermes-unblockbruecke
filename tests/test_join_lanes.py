"""Seams between the review-fix lanes: CORE caps problem lists, AGENT returns undo on a replace import,
UI's routes pass both through. Each lane stubbed the other side; these run the real modules together."""
import pytest

from ub_fakes import FakeCtx, card, deck_doc, load_plugin, make_store, sub, yaml_text


@pytest.fixture
def api(tmp_path):
    mod = sub("api")
    store = make_store(tmp_path)
    settings = sub("settings").read(lambda k, d=None: {}.get(k, d))
    mod.configure(lambda: store, lambda: settings)
    yield mod
    mod.configure(None, None)


def _broken_deck(n: int) -> str:
    # n cards, each with a non-string human face: one problem per card at least
    return yaml_text(deck_doc("many", cards=[{**card(i), "human": i} for i in range(1, n + 1)]))


def test_route_import_caps_problems_and_says_how_many_more(api):
    status, body = api.import_deck({"yaml": _broken_deck(80)})
    assert status == 422 and body["ok"] is False
    assert len(body["problems"]) == 50 and body["problems_more"] >= 30


def test_route_preview_caps_problems(api):
    doc = deck_doc("many-own", cards=[{**card(i), "human": i} for i in range(1, 81)])
    status, body = api.preview("many-own", {"content": doc})
    assert status == 422 and len(body["problems"]) == 50 and body["problems_more"] >= 30


def test_tool_preview_caps_problems_and_says_how_many_more(tmp_path):
    ctx = FakeCtx(tmp_path / "data")
    load_plugin().register(ctx)
    doc = deck_doc("many-own", cards=[{**card(i), "human": i} for i in range(1, 81)])
    out = ctx.call("unblockbruecke_decks", action="preview", deck="many-own", content=doc)
    assert out["ok"] is False and len(out["problems"]) == 50 and out["problems_more"] >= 30, out


def test_route_replace_import_answers_undo_and_undo_restores_the_old_deck(api):
    first = yaml_text(deck_doc("mine", n=3))
    assert api.import_deck({"yaml": first})[0] == 200
    second = yaml_text(deck_doc("mine", n=5))
    status, body = api.import_deck({"yaml": second, "replace": True})
    assert status == 200 and body.get("undo"), body
    status, back = api.restore("mine", {"version": body["undo"]["restore"]})
    assert status == 200, back
    status, deck = api.deck_get("mine")
    assert len(deck["deck"]["cards"]) == 3


def test_switch_with_a_list_for_deck_is_a_400_not_a_500(api):
    status, body = api.switch({"deck": ["coding"], "draw": False})
    assert status == 400 and body["error"] == "invalid"
