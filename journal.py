"""The journal: every draw, what happened next, and ratings.

One append-only JSON Lines file per month, `journal/<YYYY-MM>.jsonl` (month in Hermes' zone),
written under the data folder's lock (the gateway, a `chat -q` process and the plugin host child
all write). A rating or an outcome is a later line with the same
`draw_id`; nothing is ever rewritten. Lines are flushed, not fsynced: a power cut can lose the
newest lines of a journal, never the decks.

Weights: from explicit ratings only, `2 * (helped + 1) / (helped + not_now + 2)` per card, clamped to
[`FLOOR`, `CEILING`]: a card never rated weighs 1.0, a card that helped is drawn a little more often,
and none disappears. Unrated draws change nothing. A `reset` line starts the count again.

The read side works on a list of rows, so one draw reads the files once (`rows()`), then derives
recent draws and weights from that list. `rows()` keeps the parsed rows per file (keyed by inode,
size, mtime and ctime) and the derived folds per snapshot in memory, so a draw parses only the lines
written since the last call; the first call in a process parses the months once. A hand edit of a
journal file is read again at the next call, except a change in its middle made together with new
lines at its end, which is seen after a restart.
"""
from __future__ import annotations

import datetime as dt
import heapq
import os
import re
import sys
import threading
import time
import weakref
from operator import itemgetter
from pathlib import Path
from typing import Optional

from . import bridge
from .store import Store

FOLDER = "journal"
MONTH_RE = re.compile(r"^\d{4}-\d{2}\.jsonl$")
RATINGS = ("helped", "not_now")
BY = ("user", "agent", "auto")
FLOOR, CEILING = 0.15, 1.75
MONTHS_READ = 12


def uuid7() -> str:
    """A time-ordered UUID (RFC 9562 version 7)."""
    ms = int(time.time() * 1000)
    rand = int.from_bytes(os.urandom(10), "big")
    value = (ms & ((1 << 48) - 1)) << 80
    value |= 0x7 << 76
    value |= ((rand >> 62) & 0xFFF) << 64
    value |= 0b10 << 62
    value |= rand & ((1 << 62) - 1)
    h = f"{value:032x}"
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"


def _month_file(at=None) -> str:
    return f"{(at or bridge.now()).strftime('%Y-%m')}.jsonl"


def append(store: Store, row: dict) -> dict:
    row = {k: v for k, v in row.items() if v is not None and v != ""}
    with store.lock():
        store.append_jsonl((FOLDER, _month_file()), row, sync=False)
    return row


def record_draw(store: Store, *, by: str, deck: str, card: str, face: str, context: str,
                session_id: str = "", turn_id: str = "", tool: str = "", streak: Optional[int] = None,
                attached: Optional[bool] = None, where: str = "", platform: str = "") -> dict:
    """One draw line. `where`: where Hermes' turn ran, on draws by `agent` and `auto`
    (`bridge.where`); `platform` names the messaging platform when `where` is `messaging`."""
    if by not in BY:
        raise ValueError(f"by must be one of {', '.join(BY)}")
    return append(store, {"kind": "draw", "draw_id": uuid7(), "at": bridge.iso(), "by": by, "deck": deck,
                          "card": card, "face": face, "context": context, "session_id": session_id,
                          "turn_id": turn_id, "tool": tool, "streak": streak, "attached": attached,
                          "where": where if by in ("agent", "auto") else "",
                          "platform": platform if where == "messaging" else ""})


WHERE_LABELS = {"desktop": "Desktop chat", "kanban": "Kanban task", "cron": "Cron job", "cli": "CLI",
                "subagent": "Delegated task", "api": "API", "editor": "Editor", "webhook": "Webhook",
                "unknown": "Unknown"}
HERMES = ("agent", "auto")


def where_label(where: str, platform: str = "") -> str:
    """The place a person reads for a `where` code; a messaging chat names its platform."""
    if where == "messaging":
        return f"{(platform or 'Messaging').replace('_', ' ').title()} chat"
    return WHERE_LABELS.get(where, "Unknown")


def facts(item: dict) -> dict:
    """The outcome as facts. `next_call` is the next call's status in the same turn as Hermes
    counted it ("ok" or "failed"), absent when the turn made no further call; never "recovered"."""
    out: dict = {}
    nxt = item.get("next")
    if isinstance(nxt, dict) and nxt.get("status") in ("ok", "failed"):
        out["next_call"] = nxt["status"]
        if isinstance(nxt.get("tool"), str) and nxt["tool"]:
            out["next_call_tool"] = nxt["tool"]
    where = item.get("where")
    if isinstance(where, str) and where:
        out["where_label"] = where_label(where, str(item.get("platform") or ""))
    return out


def record_outcome(store: Store, draw_id: str, next_: dict) -> dict:
    return append(store, {"kind": "outcome", "draw_id": draw_id, "at": bridge.iso(), "next": next_})


def fits(row: dict) -> bool:
    """A row the read side can use: the fields it reads have the types it expects. Other
    rows (a newer line shape, a hand edit) are skipped, so they never break a draw or the journal view."""
    kind = row.get("kind")
    if not isinstance(kind, str):
        return False
    for key in ("draw_id", "at", "by", "session_id"):
        if key in row and not isinstance(row[key], str):
            return False
    if kind == "draw":
        return isinstance(row.get("deck"), str) and isinstance(row.get("card"), str)
    if kind == "rating":
        return row.get("rating") in RATINGS
    if kind == "outcome":
        return isinstance(row.get("next"), dict)
    return True


def instant(at: object, before: float = 0.0) -> float:
    """A row's `at` as seconds since the epoch; a row without a readable one keeps the instant of the
    row before it, so it stays where it was written."""
    if isinstance(at, str):
        try:
            return dt.datetime.fromisoformat(at).timestamp()
        except ValueError:
            pass
    return before


class Rows(list):
    """The rows `rows()` returns: a read-only list that remembers the snapshot it came from, so
    `since_reset`, `stats_from` and `recent_from` answer from the snapshot's cached folds instead of
    walking every row again. Callers must not change it (it is shared until the journal changes).

    The link to the snapshot is weak: a snapshot the cache replaced is freed at once, and a list that
    outlived it answers by walking its rows."""

    _snap_ref: "Optional[weakref.ref]" = None
    after_reset = False

    @property
    def snap(self) -> "Optional[_Snapshot]":
        return self._snap_ref() if self._snap_ref is not None else None


def _rows_of(snap: "_Snapshot", *parts: list, after_reset: bool = False) -> Rows:
    out = Rows()
    for part in parts:
        out.extend(part)  # extend, not Rows(a + b): no temporary list of every row
    out._snap_ref, out.after_reset = weakref.ref(snap), after_reset
    return out


class _File:
    """One month file, parsed once and then read on from where it stopped (the journal only appends)."""

    __slots__ = ("ident", "size", "mtime", "ctime", "offset", "head", "last", "rows", "ts", "tail", "tail_ts",
                 "version", "grew_from")

    def __init__(self):
        self.ident, self.size, self.mtime, self.ctime, self.offset = None, -1, -1, -1, 0
        self.head = self.last = b""  # the first bytes, and the bytes just before `offset`
        self.rows: list = []
        self.ts: list = []
        self.tail: list = []
        self.tail_ts: list = []
        self.version = 0
        self.grew_from: Optional[tuple] = None  # (version, rows) of the read this one only added lines to


class _Snapshot:
    """The ordered rows of some month files plus folds derived from them (stats, recent draws)."""

    def __init__(self, key: tuple, all_rows: list, ts: list, files: tuple = ()):
        self.key = key
        self.files = files  # the _FILES keys it was built from
        self.rows = _rows_of(self, all_rows)
        self.ts = ts
        self.newest = max(ts) if ts else float("-inf")
        self.cut = _last_reset(all_rows, 0, 0)
        self.folds: dict = {}
        self._after: Optional[Rows] = None

    def after_reset(self) -> Rows:
        if self.cut == 0:  # no reset in these rows: the same rows, and the same folds
            return self.rows
        if self._after is None:
            self._after = _rows_of(self, self.rows[self.cut:], after_reset=True)
        return self._after

    def fold(self, name, make):
        if name not in self.folds:
            f = make()
            for row in self.rows:
                f.add(row)
            self.folds[name] = f
        return self.folds[name]


_CACHE_LOCK = threading.RLock()
_FILES: "dict[str, _File]" = {}
_SNAPS: "dict[tuple, _Snapshot]" = {}
_KEEP_FILES, _KEEP_SNAPS = 64, 8
_KEEP_ROWS = 60_000  # rows kept for data folders other than the one just read (that one is always kept)
_HEAD = 256
# Fields whose values repeat from row to row: one shared string each instead of one per row.
_SHARED = frozenset(("kind", "by", "deck", "card", "face", "context", "session_id", "turn_id", "tool", "rating",
                     "where", "platform"))


def _last_reset(all_rows: list, start: int, cut: int) -> int:
    for i in range(start, len(all_rows)):
        if all_rows[i].get("kind") == "reset":
            cut = i + 1
    return cut


def _compact(row: dict) -> dict:
    return {sys.intern(k): (sys.intern(v) if k in _SHARED and isinstance(v, str) else v) for k, v in row.items()}


def _parse(lines: list, last: float) -> tuple[list, list]:
    keep, ts = [], []
    for r in lines:
        if fits(r):
            last = instant(r.get("at"), last)
            keep.append(_compact(r))
            ts.append(last)
    return keep, ts


def _read_file(store: Store, folder: Path, name: str) -> _File:
    """The parsed rows of one month file, keyed by inode, size, mtime and ctime: unchanged means no
    read; grown, with the first bytes and the bytes before the old end unchanged, means only the new
    lines are parsed; anything else (an edit, even one that keeps the size and the mtime) is read again.

    One edit goes unseen until the process restarts: a change in the middle of the file together with
    new lines at its end, when neither the first bytes nor the old last line changed."""
    path = folder / name  # `name` matched MONTH_RE and `folder` is store.path(FOLDER): no way out
    key = str(path)
    try:
        st = os.stat(path)
    except FileNotFoundError:
        _FILES.pop(key, None)
        return _File()
    ident = (st.st_dev, st.st_ino)
    f = _FILES.get(key)
    if (f is not None and f.ident == ident and f.size == st.st_size and f.mtime == st.st_mtime_ns
            and f.ctime == st.st_ctime_ns):
        return f
    grown = f is not None and f.ident == ident and st.st_size > f.size and f.offset > 0
    if grown:
        with open(path, "rb") as fh:
            head = fh.read(min(_HEAD, f.offset))
            fh.seek(max(0, f.offset - _HEAD))
            last = fh.read(f.offset - max(0, f.offset - _HEAD))
        grown = head == f.head[: len(head)] and last == f.last
    nf = _File()
    nf.ident, nf.size, nf.mtime, nf.ctime = ident, st.st_size, st.st_mtime_ns, st.st_ctime_ns
    nf.version = (f.version + 1) if f is not None else 1
    start = f.offset if grown else 0
    lines, _bad, end = store.read_jsonl_from((FOLDER, name), start)
    keep, ts = _parse(lines, f.ts[-1] if grown and f.ts else 0.0)
    nf.rows = (f.rows + keep) if grown else keep
    nf.ts = (f.ts + ts) if grown else ts
    nf.offset = end
    if grown and not f.tail:
        nf.grew_from = (f.version, len(f.rows))
    if end < st.st_size:  # a last line without its newline yet: parsed now, read again once complete
        tail, _bad, _end = store.read_jsonl_from((FOLDER, name), end, partial=True)
        nf.tail, nf.tail_ts = _parse(tail, nf.ts[-1] if nf.ts else 0.0)
    with open(path, "rb") as fh:
        nf.head = fh.read(_HEAD)
        fh.seek(max(0, end - _HEAD))
        nf.last = fh.read(end - max(0, end - _HEAD))
    _FILES.pop(key, None)
    _FILES[key] = nf
    while len(_FILES) > _KEEP_FILES:
        _FILES.pop(next(iter(_FILES)))
    return nf


def _ordered(files: list) -> tuple[list, list]:
    """Every row of the files in one order: each file keeps its own order (lines are appended in the
    order they happen), and the files are merged by instant, so a line that a zone change put into an
    earlier-named file still lands after the lines it followed. A row dated ahead (a clock that ran
    ahead once) stays where it was written instead of moving every later line before it."""
    parts = [list(zip(f.ts + f.tail_ts, f.rows + f.tail)) for f in files]
    merged = parts[0] if len(parts) == 1 else list(heapq.merge(*parts, key=itemgetter(0)))
    return [r for _t, r in merged], [t for t, _r in merged]


def _grow(old: _Snapshot, key: tuple, added: list, added_ts: list) -> _Snapshot:
    """A new snapshot from the old one when the journal only grew at its end (the usual append): the
    folds move over and take the new rows, so no fold walks the whole journal again."""
    n = len(old.rows)
    snap = _Snapshot.__new__(_Snapshot)
    snap.key = key
    snap.files = old.files
    snap.rows = _rows_of(snap, old.rows, added)
    snap.ts = old.ts  # shared and extended: only the cached snapshot's instants are read again
    snap.ts.extend(added_ts)
    snap.newest = max([old.newest, *added_ts])
    snap.cut = _last_reset(snap.rows, n, old.cut)
    snap._after = None
    snap.folds = old.folds
    old.folds = {}
    for f in snap.folds.values():
        for row in added:
            f.add(row)
    return snap


def _appended(old: _Snapshot, key: tuple, files: list) -> Optional[tuple[list, list]]:
    """(new rows, their instants) when the journal only grew at the end of its last file since `old`
    and the merge puts them last: the old order ended with that file's last row (every other file
    was used up before it), or no new row is earlier than the newest old one. Else None (rebuild)."""
    if len(old.key) != len(key) or not files or any(a != b for a, b in zip(old.key[:-1], key[:-1])):
        return None
    last, (name, version, _n, tail) = files[-1], old.key[-1]
    if key[-1][0] != name or tail or last.grew_from != (version, _n):
        return None
    new_rows, new_ts = last.rows[_n:] + last.tail, last.ts[_n:] + last.tail_ts
    ends_with_last = bool(_n) and bool(old.rows) and old.rows[-1] is last.rows[_n - 1]
    if not ends_with_last and new_ts and new_ts[0] < old.newest:
        return None
    return new_rows, new_ts


def _trim(current: tuple) -> None:
    """Keep at most `_KEEP_SNAPS` snapshots and `_KEEP_ROWS` rows for data folders other than `current`:
    the oldest go first, with the month files no kept snapshot uses."""
    total = sum(len(s.rows) for s in _SNAPS.values())
    for k in list(_SNAPS):
        if len(_SNAPS) <= _KEEP_SNAPS and total <= _KEEP_ROWS:
            break
        if k == current:
            continue
        total -= len(_SNAPS.pop(k).rows)
    used = {fk for s in _SNAPS.values() for fk in s.files}
    for fk in [fk for fk in _FILES if fk not in used]:
        del _FILES[fk]


def rows(store: Store, months: int = MONTHS_READ) -> list[dict]:
    """Every usable line of the newest `months` files, in the order they happened, oldest first.

    Month files are named in Hermes' zone, so after a zone change a later line can sit in an
    earlier-named file; merging the files by instant (`at`) puts it back in order, and each file keeps
    its own line order. Parsed rows are cached per file (inode, size, mtime, ctime) and per snapshot,
    so a draw reads only the lines written since the last one. The list is shared: read it, never
    change it."""
    names = [n for n in store.listdir(FOLDER) if MONTH_RE.fullmatch(n)][-months:]
    with _CACHE_LOCK:
        folder = store.path(FOLDER)
        files = [_read_file(store, folder, n) for n in names]
        key = tuple((n, f.version, len(f.rows), len(f.tail)) for n, f in zip(names, files))
        skey = (str(store.root), months)
        old = _SNAPS.get(skey)
        if old is not None and old.key == key:
            return old.rows
        added = _appended(old, key, files) if old is not None else None
        if added is not None:  # the usual case: lines appended to the newest file, later than every row
            snap = _grow(old, key, added[0], added[1])
        else:
            all_rows, ts = _ordered(files)
            snap = _Snapshot(key, all_rows, ts, tuple(str(folder / n) for n in names))
        _SNAPS.pop(skey, None)
        _SNAPS[skey] = snap
        _trim(skey)
        return snap.rows


def draws_from(all_rows: list[dict], limit: int = 50, session: str = "", by: str = "") -> list[dict]:
    """Draws newest first, each merged with its latest rating and its outcome lines."""
    ratings: dict[str, dict] = {}
    outcomes: dict[str, dict] = {}
    for row in all_rows:
        did = str(row.get("draw_id") or "")
        if row.get("kind") == "rating" and did:
            ratings[did] = row
        elif row.get("kind") == "outcome" and did:
            outcomes.setdefault(did, {}).update(row.get("next") or {})
    out = []
    for row in reversed(all_rows):
        if row.get("kind") != "draw":
            continue
        if session and row.get("session_id") != session:
            continue
        if by and (row.get("by") not in HERMES if by == "hermes" else row.get("by") != by):
            continue
        did = str(row.get("draw_id") or "")
        item = dict(row)
        if did in ratings:
            item["rating"] = ratings[did]["rating"]
            item["rated_by"] = ratings[did].get("by")
        if did in outcomes:
            item["next"] = outcomes[did]
        item.update(facts(item))
        out.append(item)
        if len(out) >= max(1, int(limit)):
            break
    return out


def draws(store: Store, limit: int = 50, session: str = "", by: str = "", months: int = MONTHS_READ) -> list[dict]:
    return draws_from(rows(store, months), limit, session, by)


def find_draw(store: Store, draw_id: str) -> Optional[dict]:
    for row in rows(store):
        if row.get("kind") == "draw" and row.get("draw_id") == draw_id:
            return row
    return None


def rate(store: Store, draw_id: str, rating: str, by: str = "user") -> dict:
    if rating not in RATINGS:
        raise ValueError(f"rating must be one of {', '.join(RATINGS)}")
    if not isinstance(draw_id, str) or find_draw(store, draw_id) is None:
        raise LookupError(f"no draw with id {draw_id!r} in the journal")
    return append(store, {"kind": "rating", "draw_id": draw_id, "at": bridge.iso(), "rating": rating, "by": by})


class _Stats:
    """Per "deck/card" counts, one row at a time; a rating replaces the draw's earlier rating.
    `resets`: a reset row starts the count again (the learned weights)."""

    def __init__(self, resets: bool = False):
        self.resets = resets
        self.clear()

    def clear(self):
        self.by_id: dict[str, str] = {}
        self.out: dict[str, dict] = {}
        self.latest: dict[str, str] = {}

    def add(self, row: dict) -> None:
        kind, did = row.get("kind"), str(row.get("draw_id") or "")
        if kind == "reset" and self.resets:
            self.clear()
        elif kind == "draw":
            k = f"{row.get('deck')}/{row.get('card')}"
            self.by_id[did] = k
            s = self.out.setdefault(k, {"drawn": 0, "helped": 0, "not_now": 0, "by_auto": 0, "recovered": 0})
            s["drawn"] += 1
            if row.get("by") == "auto":
                s["by_auto"] += 1
        elif kind == "rating" and did in self.by_id:
            s = self.out[self.by_id[did]]
            before, now = self.latest.get(did), str(row.get("rating") or "")
            if before in RATINGS:
                s[before] -= 1
            self.latest[did] = now
            if now in RATINGS:
                s[now] += 1
        elif kind == "outcome" and did in self.by_id and (row.get("next") or {}).get("calls_to_recover") is not None:
            self.out[self.by_id[did]]["recovered"] += 1

    def result(self) -> dict[str, dict]:
        return {k: dict(v) for k, v in self.out.items()}


def stats_from(all_rows: list[dict]) -> dict[str, dict]:
    """Per "deck/card": drawn, helped, not_now, by_auto, recovered (auto-draws whose turn recovered).
    Rows from `rows()` (or `since_reset()` of them) answer from the snapshot's cached fold."""
    if isinstance(all_rows, Rows) and all_rows.snap is not None:
        with _CACHE_LOCK:
            if all_rows.after_reset:
                return all_rows.snap.fold("stats_reset", lambda: _Stats(resets=True)).result()
            return all_rows.snap.fold("stats", _Stats).result()
    fold = _Stats()
    for row in all_rows:
        fold.add(row)
    return fold.result()


def stats(store: Store, months: int = MONTHS_READ) -> dict[str, dict]:
    return stats_from(rows(store, months))


def weight(helped: int, not_now: int) -> float:
    """From explicit ratings only: `2 * (helped + 1) / (helped + not_now + 2)`, so an unrated card weighs
    1.0 (the weight of a card never drawn), each "helped" raises it and each "not now" lowers it,
    clamped to [FLOOR, CEILING]. Unrated draws (most auto-draws) change nothing."""
    return min(CEILING, max(FLOOR, 2 * (helped + 1) / (helped + not_now + 2)))


def weights(stat: dict[str, dict]) -> dict[str, float]:
    return {k: weight(int(s.get("helped", 0)), int(s.get("not_now", 0))) for k, s in stat.items()}


def since_reset(all_rows: list[dict]) -> list[dict]:
    if isinstance(all_rows, Rows) and all_rows.snap is not None and not all_rows.after_reset:
        with _CACHE_LOCK:
            return all_rows.snap.after_reset()
    cut = _last_reset(all_rows, 0, 0)
    return all_rows[cut:]


class _Recent:
    def __init__(self, per_deck: int):
        self.per_deck = per_deck
        self.out: dict[str, list] = {}

    def add(self, row: dict) -> None:
        if row.get("kind") != "draw":
            return
        ids = self.out.setdefault(str(row.get("deck", "")), [])
        ids.insert(0, row.get("card"))
        del ids[self.per_deck:]

    def result(self) -> dict[str, list]:
        return {k: list(v) for k, v in self.out.items()}


def recent_from(all_rows: list[dict], per_deck: int = 3) -> dict[str, list]:
    """Per deck, the last `per_deck` card ids drawn, newest first."""
    if isinstance(all_rows, Rows) and all_rows.snap is not None and not all_rows.after_reset:
        with _CACHE_LOCK:
            return all_rows.snap.fold(("recent", per_deck), lambda: _Recent(per_deck)).result()
    fold = _Recent(per_deck)
    for row in all_rows:
        fold.add(row)
    return fold.result()


def recent_by_deck(store: Store, per_deck: int = 3) -> dict[str, list]:
    return recent_from(rows(store, months=2), per_deck)


# --- learning reset: a marker line; stats count only lines after the newest reset ----------

def reset_learning(store: Store, by: str = "user") -> dict:
    return append(store, {"kind": "reset", "at": bridge.iso(), "by": by})


def stats_since_reset(store: Store) -> dict[str, dict]:
    return stats_from(since_reset(rows(store)))
