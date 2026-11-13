"""Review findings of lane CORE (decks, store, journal, draw, settings): each test names
its finding id and asserts the behaviour the fix promises."""
import importlib.util
import pathlib

import pytest

from ub_fakes import card, deck_doc, make_store, sub, write_user_deck, yaml_text

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "check_deck.py"


def check_deck_module():
    spec = importlib.util.spec_from_file_location("check_deck_core_review", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


WRONG_TYPES = [
    ("human", 42), ("human", ["a", "b"]), ("human", {"a": 1}), ("human", True), ("agent", 1.5),
    ("id", 7), ("tags", "test"), ("tags", [1, 2]),
]


@pytest.mark.parametrize("field,value", WRONG_TYPES)
def test_core1_validate_refuses_wrong_typed_card_fields(field, value):
    """CORE-1: a non-string face (or any wrong-typed field) is a problem line, never an exception."""
    doc = deck_doc(cards=[{**card(1), field: value}, card(2)])
    deck, probs = sub("decks").validate(doc)
    assert deck is None and probs
    assert all(isinstance(p["message"], str) for p in probs)


@pytest.mark.parametrize("key,value", [("name", 5), ("by", ["x"]), ("license", {"a": 1}), ("mark", ["ring"]),
                                       ("faces", "human"), ("version", "1"), ("glossary", ["x"]),
                                       ("description", 3), ("deck", 9), ("cards", 7), ("cards", "abc")])
def test_core1_validate_refuses_wrong_typed_deck_fields(key, value):
    """CORE-1: wrong types at deck level are problem lines too."""
    deck, probs = sub("decks").validate(deck_doc(**{key: value}))
    assert deck is None and probs


def test_core1_catalog_survives_one_broken_user_file(tmp_path):
    """CORE-1: one deck file with a non-string face is listed as broken; drawing from the rest works."""
    decks, service = sub("decks"), sub("service")
    store = make_store(tmp_path)
    write_user_deck(store, deck_doc("good-deck"))
    write_user_deck(store, deck_doc("bad-deck", cards=[{**card(1), "human": 42}]))
    cat = decks.catalog(store)
    assert "bad-deck" in cat["broken"] and "good-deck" in cat["decks"]
    got = service.draw_card(store, {"learning": True}, deck="good-deck", record=False)
    assert got["card"]["deck"] == "good-deck"


def test_core1b_load_dir_survives_a_broken_community_deck(tmp_path):
    """CORE-1b: a community deck with `agent: 42` is one broken entry, not a plugin that fails to load."""
    decks = sub("decks")
    folder = tmp_path / "community"
    folder.mkdir()
    (folder / "bad-deck.yaml").write_text(yaml_text(deck_doc("bad-deck", cards=[{**card(1), "agent": 42}])),
                                          encoding="utf-8")
    (folder / "good-deck.yaml").write_text(yaml_text(deck_doc("good-deck")), encoding="utf-8")
    found, broken = decks._load_dir(folder, "community")
    assert set(found) == {"good-deck"} and "bad-deck" in broken


@pytest.mark.parametrize("cards", [7, "abc", [{**card(1), "human": 42}], [{**card(1), "agent": ["x"]}]])
def test_core1_check_deck_reports_instead_of_raising(tmp_path, capsys, cards):
    """CORE-1: check_deck.py prints the problems and exits 1 for `cards: 7` or a non-string face."""
    mod = check_deck_module()
    p = tmp_path / "odd-deck.yaml"
    p.write_text(yaml_text(deck_doc("odd-deck", cards=cards)), encoding="utf-8")
    assert mod.main([str(p)]) == 1
    assert "odd-deck.yaml:" in capsys.readouterr().out


def test_ui06_problems_are_capped_with_a_count_of_the_rest():
    """UI-06: at most 50 problems come back; `problems_more` says how many were left out."""
    decks = sub("decks")
    bad = [card(i, human="<b>x</b>", agent="Run `ls`") for i in range(1, 100)]  # 2 problems per card
    deck, probs = decks.validate(deck_doc(cards=bad))
    assert deck is None and len(probs) == decks.MAX_PROBLEMS == 50
    assert decks.problems_more(probs) == 148
    with pytest.raises(decks.DeckError) as err:
        decks.load_text(yaml_text(deck_doc(cards=bad)))
    assert len(err.value.problems) == 50 and err.value.problems_more == 148
    assert "and 192 more" in str(err.value)  # the message still counts every problem
    assert decks.problem_fields(err.value.problems)["problems_more"] == 148
    few, probs = decks.validate(deck_doc(cards=[card(1, human="<b>x</b>")]))
    assert len(probs) == 1 and decks.problems_more(probs) == 0
    assert "problems_more" not in decks.problem_fields(probs)


@pytest.mark.parametrize("face", ["[" * 40000, "[a](" * 10000, "a" * 40000 + ".", "x " * 20000],
                         ids=["brackets", "half-links", "one-word", "spaces"])
def test_core6_long_faces_are_refused_by_length_before_the_text_rules(face):
    """CORE-6: a face far over the limit costs no regex time: the length problem comes back at once."""
    import time

    decks = sub("decks")
    t0 = time.perf_counter()
    probs = decks.text_problems(face, "agent", decks.AGENT_MAX, "tt-01")
    assert time.perf_counter() - t0 < 0.5  # before the fix: seconds (quadratic); after: microseconds
    assert [p["rule"] for p in probs] == ["length_agent"]


def test_core6_text_rules_still_run_within_the_limit():
    """CORE-6: under the limit every rule still runs (a link at the limit is still caught)."""
    decks = sub("decks")
    for face in ("Read [the docs](somewhere) first. " + "x" * 150, "See [x](a(b)c) and [[y](z) now."):
        assert {p["rule"] for p in decks.text_problems(face, "agent", decks.AGENT_MAX, "tt-01")} == {"markdown_link"}


@pytest.mark.parametrize("text", ["cards: " + "[" * 1000 + "]" * 1000 + "\n", "cards: " + "{a: " * 1000 + "}" * 1000 + "\n",
                                  "cards:\n- " + "[x, " * 4000 + "]" * 4000 + "\n"],
                         ids=["brackets", "braces", "mixed"])
def test_core7_deep_flow_nesting_is_refused_before_parsing(text):
    """CORE-7: a small file nested far deeper than any deck answers bad_yaml at once."""
    import time

    decks = sub("decks")
    t0 = time.perf_counter()
    with pytest.raises(decks.DeckError) as err:
        decks.parse_yaml(text)
    assert time.perf_counter() - t0 < 1.0  # before the fix: 3 s and more; after: milliseconds
    assert err.value.code == "bad_yaml" and "deep" in str(err.value)


def test_core7_brackets_in_card_text_do_not_count_as_nesting():
    """CORE-7: '[' inside quoted or plain card text and flow-style tags still load."""
    decks = sub("decks")
    cards = [card(i, human=f"Open [ one more door {i}", agent=f"Close ] what you opened in step {i}.")
             for i in range(1, 41)]
    text = yaml_text(deck_doc(cards=cards)).replace("tags:\n  - test\n", "tags: [test]\n")
    assert "tags: [test]" in text
    text += "".join(f"# [[[[[[ comment {i}\n" for i in range(30))
    quoted = 'cards_note: "' + "[" * 50 + '"\n'
    assert decks.parse_yaml(text)["cards"][39]["human"] == "Open [ one more door 40"
    assert decks.parse_yaml(quoted)["cards_note"] == "[" * 50
    assert decks.parse_yaml("a: " + "[" * 20 + "]" * 20 + "\n")  # 20 levels are fine


def test_core16_a_new_shipped_deck_of_the_users_name_is_said_out_loud(tmp_path, monkeypatch):
    """CORE-16, revised by P2-CORE-S1/S3: when an update ships a deck named like the user's own deck, the
    user's file is not dropped without a word: it is listed as broken with the hint to import it under
    another name, and the shipped deck keeps its name, switch and journal."""
    decks, service, editor = sub("decks"), sub("service"), sub("editor")
    store = make_store(tmp_path)
    write_user_deck(store, deck_doc("focus", prefix="fo"))
    shipped_like = decks.load_text(yaml_text(deck_doc("focus", prefix="fc")), "focus")
    shipped_like["source"] = "community"
    monkeypatch.setitem(decks.SHIPPED, "focus", shipped_like)
    cat = decks.catalog(store)
    assert cat["decks"]["focus"]["source"] == "community"
    assert cat["broken"]["focus"] == ("the name 'focus' belongs to a community deck, so this file is not loaded; "
                                      "import it under another name to use it")
    for _ in range(5):
        assert service.draw_card(store, {}, deck="focus", record=False, cat=cat)["card"]["id"].startswith("fc-")
    assert editor.target_for(cat, "focus")[0] == "focus-own"  # an edit makes an own copy, as for any shipped deck
    assert len([d for d in decks.drawable(cat) if d["deck"] == "focus"]) == 1
    assert store.path("decks", "focus.yaml").exists()  # the user's file is kept


@pytest.mark.parametrize("value", [float("inf"), float("-inf"), 10 ** 400, "1e999"], ids=["inf", "-inf", "huge", "str"])
def test_core12_infinite_numbers_fall_to_the_default(value):
    """CORE-12: `autodraw_threshold: .inf` (valid YAML) gives the default, never OverflowError."""
    settings = sub("settings")
    got = settings.read(lambda key, default: value if key == "autodraw_threshold" else default)
    assert 2 <= got["autodraw_threshold"] <= 6
    assert settings.as_int(float("inf"), 3, 2, 6) == 3


def test_core17_draw_cost_grows_linearly_with_the_pool():
    """CORE-17: deck sizes are counted once per draw, so 990 cards cost about 10x of 99, not 100x."""
    import random
    import time

    draw = sub("draw")

    def pool(n_decks):
        out = []
        for d in range(n_decks):
            deck = {"deck": f"d{d}", "cards": [{"id": f"dd-{i:02d}", "tags": ["test"]} for i in range(1, 100)]}
            out.append(deck)
        return out

    def cost(decks):
        rng = random.Random(1)
        best = float("inf")
        for _ in range(5):  # the fastest of five runs: host load only ever adds time
            t0 = time.perf_counter()
            draw.draw(decks, recent={d["deck"]: ["dd-01", "dd-02", "dd-03"] for d in decks}, rng=rng)
            best = min(best, time.perf_counter() - t0)
        return best

    small, big = cost(pool(1)), cost(pool(10))
    assert big / small < 30  # before the fix: x79 to x100 for x10 cards


def test_core3_a_line_cut_inside_a_utf8_character_is_skipped(tmp_path):
    """CORE-3: a power cut inside a multi-byte character costs that line, not every draw."""
    store, journal, service = make_store(tmp_path), sub("journal"), sub("service")
    journal.record_draw(store, by="user", deck="coding", card="co-01", face="human", context="any")
    path = store.path("journal", "2026-11.jsonl")
    cut = '{"kind":"skipped","why":"UnblockBrü'.encode("utf-8")[:-1]  # half of the 'ü'
    with open(path, "ab") as fh:
        fh.write(cut)
    journal.record_draw(store, by="user", deck="coding", card="co-02", face="human", context="any")
    rows, bad = store.read_jsonl("journal", "2026-11.jsonl")
    assert [r["card"] for r in rows] == ["co-01", "co-02"] and bad == 1
    assert service.draw_card(store, {}, deck="coding", record=False)["card"]["deck"] == "coding"
    assert len(journal.draws(store)) == 2


WRONG_SHAPES = [
    {"kind": "outcome", "next": ["a"]}, {"kind": "outcome", "next": "ok"}, {"kind": "rating"},
    {"kind": "rating", "rating": ["helped"]}, {"kind": "rating", "rating": "great"}, {"kind": ["draw"]},
    {"kind": "draw", "deck": ["coding"], "card": "co-01"}, {"kind": "draw", "deck": "coding", "card": 7},
    {"kind": "rating", "rating": "helped", "draw_id": {"a": 1}}, {"kind": "draw", "deck": "coding", "card": "co-03", "at": 5},
]


def test_core10_wrong_shaped_journal_rows_are_skipped(tmp_path):
    """CORE-10: valid JSON of the wrong shape never breaks a draw, the journal view or the stats."""
    store, journal, service = make_store(tmp_path), sub("journal"), sub("service")
    d = journal.record_draw(store, by="user", deck="coding", card="co-01", face="human", context="any")
    for row in WRONG_SHAPES:
        journal.append(store, {"draw_id": d["draw_id"], "at": "2026-11-10T14:00:00+01:00", **row})
    journal.rate(store, d["draw_id"], "helped")
    assert service.draw_card(store, {}, deck="coding", record=False)["card"]["deck"] == "coding"
    draws = journal.draws(store)
    assert [x["card"] for x in draws] == ["co-01"] and draws[0]["rating"] == "helped"
    assert journal.stats(store)["coding/co-01"]["helped"] == 1 and len(journal.stats(store)) == 1


def _at(bridge, year, month, day, hour, minute, zone):
    import datetime as dt
    from zoneinfo import ZoneInfo

    tz = dt.timezone.utc if zone == "UTC" else ZoneInfo(zone)
    bridge.set_clock(lambda: dt.datetime(year, month, day, hour, minute, tzinfo=tz), zone)


def test_core11_a_rating_in_an_earlier_named_month_file_still_counts(tmp_path):
    """CORE-11: rows are ordered by their instant, so a zone change across a month boundary keeps a
    rating after its draw (the draw lands in 2026-12.jsonl, the rating 10 minutes later in 2026-11.jsonl)."""
    store, journal, bridge = make_store(tmp_path), sub("journal"), sub("bridge")
    _at(bridge, 2026, 12, 1, 0, 30, "Europe/Berlin")  # 2026-11-30 23:30 UTC
    d = journal.record_draw(store, by="user", deck="coding", card="co-01", face="human", context="any")
    _at(bridge, 2026, 11, 30, 23, 40, "UTC")
    journal.rate(store, d["draw_id"], "helped")
    assert store.listdir("journal") == ["2026-11.jsonl", "2026-12.jsonl"]
    assert journal.stats(store)["coding/co-01"]["helped"] == 1
    assert journal.draws(store)[0]["rating"] == "helped"


def test_core11_reset_cuts_by_instant_not_by_file_name(tmp_path):
    """CORE-11: a reset written after a rating (by the clock) clears it even when its file name sorts first."""
    store, journal, bridge = make_store(tmp_path), sub("journal"), sub("bridge")
    _at(bridge, 2026, 12, 1, 0, 30, "Europe/Berlin")
    d = journal.record_draw(store, by="user", deck="coding", card="co-01", face="human", context="any")
    journal.rate(store, d["draw_id"], "helped")
    _at(bridge, 2026, 11, 30, 23, 45, "UTC")  # 15 minutes later, but into 2026-11.jsonl
    journal.reset_learning(store)
    assert journal.stats_since_reset(store) == {}
    _at(bridge, 2026, 12, 1, 0, 10, "UTC")
    e = journal.record_draw(store, by="user", deck="coding", card="co-02", face="human", context="any")
    journal.rate(store, e["draw_id"], "helped")
    assert set(journal.stats_since_reset(store)) == {"coding/co-02"}


def test_core2_learning_raises_helped_cards_and_ignores_unrated_draws(tmp_path):
    """CORE-2: weights come from explicit ratings only (contract §4). A card rated helped weighs more
    than a never-rated one, unrated auto-draws leave a card at 1.0, not-now lowers it; floor and ceiling hold."""
    store, journal, service = make_store(tmp_path), sub("journal"), sub("service")

    def draws(card, n, rating=None, by="user"):
        for _ in range(n):
            d = journal.record_draw(store, by=by, deck="coding", card=card, face="agent", context="auto")
            if rating:
                journal.rate(store, d["draw_id"], rating)

    draws("co-01", 1, "helped")
    draws("co-02", 3, "helped")
    draws("co-03", 20, by="auto")  # drawn often, never rated
    draws("co-04", 1, "not_now")
    draws("co-05", 30, "not_now")
    draws("co-06", 40, "helped")
    w = service.learned_weights(store, {"learning": True})
    never = w.get("coding/co-99", 1.0)
    assert never == 1.0 and w["coding/co-03"] == pytest.approx(1.0)
    assert w["coding/co-02"] > w["coding/co-01"] > never > w["coding/co-04"] > w["coding/co-05"]
    assert w["coding/co-05"] == journal.FLOOR and w["coding/co-06"] == journal.CEILING
    journal.reset_learning(store)
    assert service.learned_weights(store, {"learning": True}) == {}


def _fill(root, months, per_month, card_ids):
    import datetime as dt
    import json

    (root / "journal").mkdir(parents=True, exist_ok=True)
    for m in range(1, months + 1):
        with open(root / "journal" / f"2026-{m:02d}.jsonl", "w", encoding="utf-8") as fh:
            for i in range(per_month):
                at = (dt.datetime(2026, m, 1, tzinfo=dt.timezone.utc) + dt.timedelta(minutes=i)).isoformat()
                fh.write(json.dumps({"kind": "draw", "draw_id": f"{m}-{i}", "at": at, "by": "auto", "deck": "agent-unblock",
                                     "card": card_ids[i % len(card_ids)], "face": "agent", "context": "auto"}) + "\n")


def test_core8_a_draw_does_not_reparse_the_whole_journal(tmp_path):
    """CORE-8: with 11 000 journal lines a draw that writes its line costs about what it costs with 100
    (before the fix: x50 and more, every draw parsed 12 months)."""
    import statistics
    import time

    decks, service, store_mod = sub("decks"), sub("service"), sub("store")
    ids = [c["id"] for c in decks.SHIPPED["agent-unblock"]["cards"]]
    settings = {"learning": True, "autodraw_decks": ["agent-unblock"]}

    def cost(root):
        store = store_mod.Store(root)
        cat = decks.catalog(store)
        service.draw_card(store, settings, context="auto", by="auto", cat=cat)  # the first read in this process
        out = []
        for _ in range(7):
            t0 = time.perf_counter()
            service.draw_card(store, settings, context="auto", by="auto", cat=cat)
            out.append(time.perf_counter() - t0)
        return statistics.median(out)

    _fill(tmp_path / "small" / "data", 1, 100, ids)
    _fill(tmp_path / "big" / "data", 11, 1000, ids)
    small, big = cost(tmp_path / "small" / "data"), cost(tmp_path / "big" / "data")
    assert big / small < 10, (big, small)


def test_core8_cached_reads_match_a_fresh_read(tmp_path):
    """CORE-8: the cached stats, recent draws and draws equal a fresh fold over the same rows after
    appends from another Store object (another process), a rating change, a reset and a rewritten file."""
    import json

    journal, store_mod = sub("journal"), sub("store")
    store = make_store(tmp_path)
    other = store_mod.Store(store.root)

    def same():
        rows = journal.rows(store)
        plain = [dict(r) for r in rows]
        assert journal.stats(store) == journal.stats_from(plain)
        assert journal.stats_since_reset(store) == journal.stats_from(journal.since_reset(plain))
        assert journal.recent_from(rows) == journal.recent_from(plain)
        assert journal.draws(store) == journal.draws_from(plain)

    ids = []
    for i in range(6):
        ids.append(journal.record_draw(store, by="user", deck="coding", card=f"co-0{i % 4 + 1}", face="human",
                                       context="any")["draw_id"])
        same()
    journal.rate(other, ids[0], "helped")
    same()
    assert journal.stats(store)["coding/co-01"]["helped"] == 1
    journal.rate(other, ids[0], "not_now")  # the latest rating counts
    same()
    assert journal.stats(store)["coding/co-01"] == {**journal.stats(store)["coding/co-01"], "helped": 0, "not_now": 1}
    journal.reset_learning(other)
    same()
    assert journal.stats_since_reset(store) == {}
    journal.record_outcome(other, ids[5], {"calls_to_recover": 1})
    journal.rate(store, ids[5], "helped")
    same()
    path = store.path("journal", "2026-11.jsonl")
    kept = path.read_text(encoding="utf-8").splitlines()[:2]  # a hand edit: the file shrinks
    path.write_text("\n".join(kept) + "\n", encoding="utf-8")
    same()
    assert len(journal.draws(store)) == 2
    with open(path, "a", encoding="utf-8") as fh:  # a valid line without its newline yet
        fh.write(json.dumps({"kind": "draw", "draw_id": "x", "at": "2026-11-10T14:00:00+01:00", "deck": "coding",
                             "card": "co-09"}))
    same()
    assert journal.draws(store)[0]["card"] == "co-09"
    journal.record_draw(store, by="user", deck="coding", card="co-10", face="human", context="any")
    same()
    assert [d["card"] for d in journal.draws(store)][:2] == ["co-10", "co-09"]


# --- round 2 (second-pass findings) --------------------------------------------------------------

def _timed_parse(text):
    import time

    decks = sub("decks")
    t = time.perf_counter()
    try:
        decks.parse_yaml(text)
        out = "parsed"
    except decks.DeckError as exc:
        out = exc.code
    return time.perf_counter() - t, out


@pytest.mark.parametrize("lead", ["[a'b, ", '[a"b, ', '"open, [', "[it's, ", '[x, "y'])
def test_p2_core_v3_a_quote_inside_a_plain_scalar_does_not_switch_the_depth_scan_off(lead):
    """P2-CORE-V3: a lone or mid-scalar quote before deep nesting still gets the nesting refused at once."""
    text = "x: " + lead + "[" * 1000 + "]" * 1000 + "]\n"
    took, out = _timed_parse(text)
    assert out == "bad_yaml" and took < 0.5, (took, out)


NEST = "[" * 1000 + "]" * 1000


@pytest.mark.parametrize("text", [
    'x: Step - "a\ny: ' + NEST + '\nz: b"\n',  # a dash inside plain text is no block indicator
    'x: text\n  "q\ny: ' + NEST + '\nz: a"\n',  # a quote at the start of a plain scalar's next line
    'x: |\n  "start\ny: ' + NEST + '\nz: end"\n',  # a quote inside a literal block
    'x: [Step - "a ' + NEST + ' b"]\n',  # a dash inside a flow collection
], ids=["dash-in-plain", "plain-next-line", "literal-block", "dash-in-flow"])
def test_p2_core_v3_a_misread_quote_cannot_hide_the_lines_after_it(text):
    """P2-CORE-V3: a quote the pre-scan cannot be sure of hides nothing beyond its own line."""
    took, out = _timed_parse(text)
    assert out == "bad_yaml" and took < 0.5, (took, out)


def test_p2_core_v3_many_groups_under_the_parser_limit_are_refused_fast():
    """P2-CORE-V3: groups of depth 300 after one lone quote are past the limit, refused before the parser."""
    group = "[" * 300 + "]" * 300
    took, out = _timed_parse('x: [a"b, ' + ", ".join([group] * 16) + "]\n")
    assert out == "bad_yaml" and took < 0.5, (took, out)


def test_p2_core_v5_emoticons_in_card_text_are_not_nesting():
    """P2-CORE-V5: 22 cards with ':[' in plain text load (a ':' opens a value only before whitespace)."""
    decks = sub("decks")
    cards = [card(i + 1, "em", human=f"Stuck again :[ card {i}", agent=f"Note it :[ and try step {i}.")
             for i in range(22)]
    deck = decks.load_text(yaml_text(deck_doc("emo-deck", cards=cards)), "emo-deck")
    assert deck["cards"][21]["human"] == "Stuck again :[ card 21"
    assert decks.parse_yaml("a: " + "[" * 20 + "]" * 20 + "\n")  # 20 levels still load
    assert _timed_parse("a: " + "[" * 21 + "]" * 21 + "\n")[1] == "bad_yaml"
    assert _timed_parse("a:\n- " + "[" * 21 + "]" * 21 + "\n")[1] == "bad_yaml"


def _user_file_named(tmp_path, slug, prefix="zz"):
    store = make_store(tmp_path)
    write_user_deck(store, deck_doc(slug, n=3, prefix=prefix))
    return store


def test_p2_core_s3_a_user_file_named_like_the_shipped_auto_deck_never_reaches_auto_draw(tmp_path):
    """P2-CORE-S3: a hand-placed decks/agent-unblock.yaml is refused with a rename hint; auto-draw with the
    default settings keeps drawing the shipped deck."""
    decks, service, settings = sub("decks"), sub("service"), sub("settings")
    store = _user_file_named(tmp_path, "agent-unblock")
    cat = decks.catalog(store)
    assert cat["decks"]["agent-unblock"]["source"] == "shipped"
    reason = cat["broken"]["agent-unblock"]
    assert "shipped deck" in reason and "another name" in reason
    picks = {service.draw_card(store, dict(settings.DEFAULTS), context="auto", by="auto", record=False,
                               unattended=True, cat=cat)["card"]["id"] for _ in range(40)}
    assert picks and all(p.startswith("ag-") for p in picks), picks


def test_p2_core_s1_the_shipped_deck_stays_drawable_and_showable_and_keeps_its_switch(tmp_path):
    """P2-CORE-S1: with a user file human-unblock.yaml the shipped deck is still drawn, shown and switched as
    before; the user's file takes neither its switch nor its learned weights (it is not loaded at all)."""
    decks, service, journal = sub("decks"), sub("service"), sub("journal")
    store = make_store(tmp_path)
    decks.set_switch(store, "human-unblock", auto=False)
    for _ in range(3):
        d = journal.record_draw(store, by="user", deck="human-unblock", card="hu-01", face="human", context="any")
        journal.rate(store, d["draw_id"], "not_now")
    write_user_deck(store, deck_doc("human-unblock", n=3, prefix="hu"))
    cat = decks.catalog(store)
    deck = cat["decks"]["human-unblock"]
    assert deck["source"] == "shipped" and len(deck["cards"]) == len(decks.SHIPPED["human-unblock"]["cards"])
    assert deck["switch"] == {"draw": True, "auto": False}
    assert "human-unblock" in cat["broken"]
    shipped_ids = {c["id"] for c in decks.SHIPPED["human-unblock"]["cards"]}
    drawn = {service.draw_card(store, {}, deck="human-unblock", record=False, cat=cat)["card"]["human"] for _ in range(30)}
    assert drawn <= {c["human"] for c in decks.SHIPPED["human-unblock"]["cards"]}
    assert service.show(store, "human-unblock", sorted(shipped_ids)[1], cat=cat)["deck"] == "human-unblock"
    assert all(d["deck"] != "human-unblock" or d["source"] == "shipped" for d in decks.drawable(cat))


def test_p2_core_d1_catalog_parses_an_unchanged_user_deck_once(tmp_path, monkeypatch):
    """P2-CORE-D1: catalog() keeps parsed user decks by path, size and times; only a changed file is read again,
    even when an edit keeps the size and puts the old mtime back."""
    import os

    decks = sub("decks")
    store = make_store(tmp_path)
    path = write_user_deck(store, deck_doc("mine", n=4, prefix="mi"))
    for n in range(2, 6):
        write_user_deck(store, deck_doc(f"mine-{n}", n=4, prefix="mi"))
    calls = []
    real = decks.parse_yaml
    monkeypatch.setattr(decks, "parse_yaml", lambda text: calls.append(1) or real(text))
    first = decks.catalog(store)
    assert len(first["decks"]) - len(decks.SHIPPED) == 5
    calls.clear()
    for _ in range(3):
        again = decks.catalog(store)
    assert calls == [] and again["decks"]["mine"]["cards"] == first["decks"]["mine"]["cards"]
    st = os.stat(path)
    text = path.read_text(encoding="utf-8")
    edited = text.replace("Human line number 1.", "Human line number 9.")
    assert len(edited) == len(text) and edited != text
    path.write_text(edited, encoding="utf-8")
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns))  # same size, old mtime
    assert decks.catalog(store)["decks"]["mine"]["cards"][0]["human"] == "Human line number 9."
    assert len(calls) == 1
    again = decks.catalog(store)
    again["decks"]["mine"]["cards"].clear()  # a caller that changes its copy does not change the cache
    assert decks.catalog(store)["decks"]["mine"]["cards"][0]["human"] == "Human line number 9."


def test_p2_core_d1_a_deck_file_linked_from_outside_the_data_folder_stays_out(tmp_path):
    """P2-CORE-D1: the faster path check still refuses a user deck file that links out of the data folder."""
    decks = sub("decks")
    store = make_store(tmp_path)
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (outside / "linked.yaml").write_text(yaml_text(deck_doc("linked", prefix="li")), encoding="utf-8")
    store.path("decks").mkdir(parents=True)
    store.path("decks", "inside.yaml").write_text(yaml_text(deck_doc("inside", prefix="in")), encoding="utf-8")
    (store.root / "decks" / "linked.yaml").symlink_to(outside / "linked.yaml")
    cat = decks.catalog(store)
    assert "linked" not in cat["decks"] and "leaves the data folder" in cat["broken"]["linked"]
    assert "inside" in cat["decks"]
