"""Parent fix after round 2: a save to `<shipped>-own` that does not exist yet starts from the shipped
deck (an own copy), never an unrelated new deck that then hides the shipped one (P2-UI-01, route half)."""
from ub_fakes import card, deck_doc, make_store, sub


def test_new_deck_named_like_an_own_copy_starts_from_the_shipped_deck(tmp_path):
    editor, decks = sub("editor"), sub("decks")
    store = make_store(tmp_path)
    cat = decks.catalog(store)
    shipped = cat["decks"]["coding"]
    target, base = editor.target_for(cat, "coding-own")
    assert target == "coding-own"
    assert base is not None and base["deck"] == "coding" and len(base["cards"]) == len(shipped["cards"])


def test_preview_of_a_one_card_coding_own_keeps_the_shipped_cards(tmp_path):
    editor, decks = sub("editor"), sub("decks")
    store = make_store(tmp_path)
    shipped_n = len(decks.catalog(store)["decks"]["coding"]["cards"])
    change = {"add": [{"human": "Hum it to the cat.", "agent": "Ask the user to hum the hook once and say what they noticed.",
                       "tags": ["test"]}]}
    pv = editor.preview(store, "coding-own", None, change)
    assert pv["ok"], pv
    assert pv["target"] == "coding-own"
    assert pv["cards"] == shipped_n + 1
