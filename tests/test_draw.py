"""Drawing: context filters, no repeats, weights, card of the day, the shared draw path."""
import datetime as dt
import random

import pytest

from ub_fakes import SeqRng, card, deck_doc, make_store, sub, write_user_deck, yaml_text


def load(doc):
    d = sub("decks").load_text(yaml_text(doc), doc["deck"])
    d["source"] = "own"
    return d


def mixed_deck():
    return load(deck_doc("mix", cards=[card(1, tags=["auto"]), card(2, tags=["human"]), card(3, tags=["test"]),
                                       card(4, tags=["auto", "human"]), card(5, tags=["lateral"])]))


def test_faces_follow_context():
    draw = sub("draw")
    assert draw.face_for("stuck") == "agent" and draw.face_for("auto") == "agent"
    assert draw.face_for("break") == "human" and draw.face_for("human") == "human" and draw.face_for("any") == "human"


def test_auto_prefers_auto_cards_and_unattended_skips_human():
    draw = sub("draw")
    deck = mixed_deck()
    ids = lambda pairs: [c["id"] for _, c in pairs]  # noqa: E731
    assert ids(draw.candidates([deck], "auto")) == ["tt-01", "tt-04"]
    assert ids(draw.candidates([deck], "auto", unattended=True)) == ["tt-01"]
    assert ids(draw.candidates([deck], "any", unattended=True)) == ["tt-01", "tt-03", "tt-05"]
    assert ids(draw.candidates([deck], "any", tags=["lateral"])) == ["tt-05"]


def test_auto_never_falls_back_to_cards_not_written_for_it():
    """0.2 (AX-6): auto-draw uses only `auto` cards; 0.1 fell back to every card of the deck."""
    draw = sub("draw")
    deck = load(deck_doc())
    assert draw.candidates([deck], "auto") == []


def test_no_repeat_of_the_last_three():
    draw = sub("draw")
    deck = load(deck_doc(n=5))
    seen = set()
    for seed in range(60):
        got = draw.draw([deck], recent={"test-deck": ["tt-01", "tt-02", "tt-03", "tt-04"]}, rng=random.Random(seed))
        seen.add(got["card"]["id"])
    assert seen == {"tt-04", "tt-05"}  # only the newest three are left out


def test_small_deck_may_repeat():
    draw = sub("draw")
    deck = load(deck_doc(n=3))
    got = draw.draw([deck], recent={"test-deck": ["tt-01", "tt-02", "tt-03"]}, rng=random.Random(1))
    assert got["card"]["id"] in {"tt-01", "tt-02", "tt-03"}


def test_weights_shift_the_odds():
    draw = sub("draw")
    deck = load(deck_doc(n=2))
    rng = random.Random(7)
    counts = {"tt-01": 0, "tt-02": 0}
    for _ in range(2000):
        counts[draw.draw([deck], weights={"test-deck/tt-01": 0.9, "test-deck/tt-02": 0.15}, rng=rng)["card"]["id"]] += 1
    assert counts["tt-01"] > 4 * counts["tt-02"] > 0


def test_no_card_raises():
    draw = sub("draw")
    with pytest.raises(draw.NoCard):
        draw.draw([], rng=random.Random(1))
    with pytest.raises(ValueError):
        draw.draw([load(deck_doc())], context="sideways")


def test_card_of_day_is_stable_per_date():
    draw = sub("draw")
    deck = load(deck_doc(n=24))
    a = draw.card_of_day(deck, dt.date(2026, 11, 10))["card"]["id"]
    assert a == draw.card_of_day(deck, dt.date(2026, 11, 10))["card"]["id"]
    days = {draw.card_of_day(deck, dt.date(2026, 11, d))["card"]["id"] for d in range(1, 29)}
    assert len(days) > 8


def test_card_view_shape():
    draw = sub("draw")
    deck = load(deck_doc())
    view = draw.card_view(deck, deck["cards"][0], "agent")
    assert view["directive"] == '::card{deck="test-deck" id="tt-01"}'
    assert view["why"] == [{"tag": "test", "means": "A tag used in tests."}]
    assert set(view) >= {"deck", "deck_name", "mark", "id", "human", "agent", "tags", "face"}


def test_service_draw_records_and_respects_preferred_deck(tmp_path, monkeypatch):
    decks, service, journal = sub("decks"), sub("service"), sub("journal")
    monkeypatch.setattr(decks, "SHIPPED", {})
    store = make_store(tmp_path)
    write_user_deck(store, deck_doc("human-unblock", prefix="hu"))
    write_user_deck(store, deck_doc("agent-unblock", prefix="ag", cards=[card(1, "ag", tags=["auto"]), card(2, "ag")]))
    out = service.draw_card(store, {"learning": True}, context="break", by="agent", rng=SeqRng([0]))
    assert out["card"]["deck"] == "human-unblock" and out["card"]["face"] == "human"
    stuck = service.draw_card(store, {"learning": True}, context="stuck", rng=SeqRng([0]))
    assert stuck["card"]["deck"] == "agent-unblock" and stuck["card"]["face"] == "agent"
    auto = service.draw_card(store, {"autodraw_decks": ["agent-unblock"]}, context="auto", by="auto", rng=SeqRng([0]))
    assert auto["card"]["id"] == "ag-01"
    rows = journal.draws(store)
    assert [r["by"] for r in rows] == ["auto", "user", "agent"]
    with pytest.raises(LookupError):
        service.draw_card(store, {}, deck="nope")


def test_card_of_day_service_respects_setting(tmp_path, monkeypatch):
    decks, service = sub("decks"), sub("service")
    monkeypatch.setattr(decks, "SHIPPED", {})
    store = make_store(tmp_path)
    write_user_deck(store, deck_doc("human-unblock", prefix="hu"))
    assert service.card_of_day(store, {"card_of_day": False}) is None
    day = service.card_of_day(store, {"card_of_day": True})
    assert day["date"] == "2026-11-10" and day["card"]["face"] == "human"
