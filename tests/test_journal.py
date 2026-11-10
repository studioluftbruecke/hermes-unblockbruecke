"""The journal: append-only months, ratings, outcomes, stats, weights, reset."""
import threading

import pytest

from ub_fakes import make_store, sub


def test_uuid7_shape_and_order():
    journal = sub("journal")
    a, b = journal.uuid7(), journal.uuid7()
    assert len(a) == 36 and a[14] == "7" and a[19] in "89ab"
    assert a[:13] <= b[:13]


def test_draw_rate_outcome_merge(tmp_path):
    journal = sub("journal")
    store = make_store(tmp_path)
    d = journal.record_draw(store, by="auto", deck="agent-unblock", card="ag-03", face="agent", context="auto",
                            session_id="s1", turn_id="t1", tool="terminal", streak=3, attached=True)
    journal.record_outcome(store, d["draw_id"], {"status": "ok", "tool": "read_file"})
    journal.record_outcome(store, d["draw_id"], {"calls_to_recover": 1})
    journal.rate(store, d["draw_id"], "helped")
    rows = journal.draws(store)
    assert rows[0]["rating"] == "helped" and rows[0]["next"] == {"status": "ok", "tool": "read_file", "calls_to_recover": 1}
    assert store.listdir("journal") == ["2026-11.jsonl"]  # month in Hermes' zone
    lines, bad = store.read_jsonl("journal", "2026-11.jsonl")
    assert [r["kind"] for r in lines] == ["draw", "outcome", "outcome", "rating"] and bad == 0
    assert "args" not in lines[0]  # the plugin logs no tool arguments


def test_rate_refuses_unknown_draw_and_bad_rating(tmp_path):
    journal = sub("journal")
    store = make_store(tmp_path)
    with pytest.raises(LookupError):
        journal.rate(store, "nope", "helped")
    d = journal.record_draw(store, by="user", deck="x", card="x-01", face="human", context="any")
    with pytest.raises(ValueError):
        journal.rate(store, d["draw_id"], "great")
    with pytest.raises(ValueError):
        journal.record_draw(store, by="robot", deck="x", card="x-01", face="human", context="any")


def test_stats_and_weights(tmp_path):
    journal = sub("journal")
    store = make_store(tmp_path)
    ids = [journal.record_draw(store, by="user", deck="d", card="d-01", face="human", context="any")["draw_id"]
           for _ in range(4)]
    journal.rate(store, ids[0], "helped")
    journal.rate(store, ids[1], "helped")
    journal.rate(store, ids[1], "not_now")  # the latest rating of a draw counts
    journal.record_draw(store, by="user", deck="d", card="d-02", face="human", context="any")
    st = journal.stats(store)
    assert st["d/d-01"] == {"drawn": 4, "helped": 1, "not_now": 1, "by_auto": 0, "recovered": 0}
    w = journal.weights(st)
    # CORE-2: from ratings only; one helped and one not-now cancel out, unrated draws change nothing
    assert w["d/d-01"] == pytest.approx(1.0) and w["d/d-02"] == pytest.approx(1.0)
    many = {"x/x-01": {"drawn": 100, "helped": 0, "not_now": 100}}
    assert journal.weights(many)["x/x-01"] == journal.FLOOR  # no card disappears


def test_reset_clears_learning(tmp_path):
    journal = sub("journal")
    store = make_store(tmp_path)
    d = journal.record_draw(store, by="user", deck="d", card="d-01", face="human", context="any")
    journal.rate(store, d["draw_id"], "helped")
    assert journal.stats_since_reset(store)["d/d-01"]["helped"] == 1
    journal.reset_learning(store)
    assert journal.stats_since_reset(store) == {}
    assert journal.draws(store)[0]["rating"] == "helped"  # the journal itself is kept


def test_recent_by_deck(tmp_path):
    journal = sub("journal")
    store = make_store(tmp_path)
    for i in range(1, 6):
        journal.record_draw(store, by="user", deck="d", card=f"d-0{i}", face="human", context="any")
    assert journal.recent_by_deck(store) == {"d": ["d-05", "d-04", "d-03"]}


def test_concurrent_appends_keep_every_line(tmp_path):
    journal = sub("journal")
    store = make_store(tmp_path)

    def work():
        for _ in range(25):
            journal.record_draw(store, by="auto", deck="d", card="d-01", face="agent", context="auto")

    threads = [threading.Thread(target=work) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    lines, bad = store.read_jsonl("journal", "2026-11.jsonl")
    assert len(lines) == 200 and bad == 0


# --- round 2: the journal cache's edges (second pass) ----------------------------------------------

def _warm_and_fresh(journal, store):
    """(what this process's cache answers, what a fresh process reads) for stats, weights and draws."""
    warm = (journal.stats(store), journal.stats_since_reset(store), journal.draws(store, limit=200))
    with journal._CACHE_LOCK:
        journal._FILES.clear()
        journal._SNAPS.clear()
    fresh = (journal.stats(store), journal.stats_since_reset(store), journal.draws(store, limit=200))
    return warm, fresh


def _draws(journal, store, n, start=1):
    return [journal.record_draw(store, by="user", deck="coding", card=f"co-{i:02d}", face="human",
                                context="any")["draw_id"] for i in range(start, start + n)]


def test_journal_cache_sees_a_same_size_edit_that_restores_the_mtime(tmp_path):
    """Journal cache edges (P2-CORE-J2): an in-place edit that keeps the size and puts the old mtime back."""
    import os
    import time

    journal = sub("journal")
    store = make_store(tmp_path)
    _draws(journal, store, 6)
    journal.stats(store)  # warm
    path = store.path("journal", "2026-11.jsonl")
    time.sleep(0.05)  # a hand edit comes later than the last write; ctime ticks coarsely (~4 ms), so an edit
    # inside the same tick as the previous write keeps every stamp and is seen only after the next write
    st = os.stat(path)
    text = path.read_text(encoding="utf-8")
    edited = text.replace('"card":"co-02"', '"card":"co-09"')
    assert len(edited) == len(text) and edited != text
    path.write_text(edited, encoding="utf-8")
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns))
    warm, fresh = _warm_and_fresh(journal, store)
    assert warm == fresh and "coding/co-09" in warm[0]


def test_journal_cache_sees_an_edit_that_grows_the_file(tmp_path):
    """Journal cache edges (P2-CORE-J3): an in-place edit one byte longer is not taken for an append."""
    journal = sub("journal")
    store = make_store(tmp_path)
    ids = _draws(journal, store, 8)
    journal.rate(store, ids[6], "helped")
    journal.rate(store, ids[7], "helped")
    journal.stats(store)  # warm
    path = store.path("journal", "2026-11.jsonl")
    text = path.read_text(encoding="utf-8")
    at = text.index('"rating":"helped"')
    assert at > 256  # past the head the cache compares
    path.write_text(text[:at] + '"rating":"not_now"' + text[at + len('"rating":"helped"'):], encoding="utf-8")
    warm, fresh = _warm_and_fresh(journal, store)
    assert warm == fresh and warm[0]["coding/co-07"]["not_now"] == 1
    journal.stats(store)
    _draws(journal, store, 1, start=20)
    warm, fresh = _warm_and_fresh(journal, store)
    assert warm == fresh


def test_journal_a_future_dated_row_does_not_take_later_draws_off_the_append_path(tmp_path, monkeypatch):
    """Journal cache edges (P2-CORE-D3): one row dated a day ahead (a clock that ran ahead once) does not make
    every later read rebuild the whole journal; the cached answer still equals a fresh read."""
    journal = sub("journal")
    store = make_store(tmp_path)
    _draws(journal, store, 5)
    journal.append(store, {"kind": "draw", "draw_id": "future", "at": "2026-11-11T14:00:00+01:00", "by": "user",
                           "deck": "coding", "card": "co-50", "face": "human", "context": "any"})
    journal.rows(store)
    builds = []
    real = journal._Snapshot.__init__

    def counting(self, *a, **k):
        builds.append(1)
        real(self, *a, **k)

    monkeypatch.setattr(journal._Snapshot, "__init__", counting)
    for i in range(5):
        _draws(journal, store, 1, start=10 + i)
        journal.rows(store)
    assert builds == []
    monkeypatch.undo()
    warm, fresh = _warm_and_fresh(journal, store)
    assert warm == fresh


def test_journal_cache_frees_replaced_snapshots_and_bounds_other_data_folders(tmp_path, monkeypatch):
    """Journal cache edges (P2-CORE-M1): a replaced snapshot is freed at once (no reference cycle waits for the
    collector), and the rows kept for other data folders stay under the row budget."""
    import gc
    import weakref

    journal = sub("journal")
    store = make_store(tmp_path)
    _draws(journal, store, 3)
    rows = journal.rows(store)
    ref = weakref.ref(rows.snap)
    gc.disable()
    try:
        _draws(journal, store, 1, start=9)
        journal.rows(store)
        assert ref() is None
    finally:
        gc.enable()
    assert journal.stats_from(rows) == journal.stats_from(list(rows))  # an old list still answers
    monkeypatch.setattr(journal, "_KEEP_ROWS", 50)
    for n in range(6):
        other = make_store(tmp_path / f"f{n}")
        _draws(journal, other, 20)
        journal.rows(other)
    with journal._CACHE_LOCK:
        kept = sum(len(f.rows) + len(f.tail) for f in journal._FILES.values())
    assert kept <= 50 + 20, kept
