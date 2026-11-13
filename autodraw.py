"""Hermes draws when stuck (F6, F7; 0.2 M2): the `transform_tool_result` hook.

When the setting `autodraw` is on and `autodraw_threshold` of the last `threshold + 2` tool calls of a
turn failed (D16: 3 of the last 5 by default; any tools), the failing result that reaches the count
carries one card. One card per turn (AX-8). The count stays per turn: M0 P1 found no fire that carrying
it across the turns of a chat adds (D17 not supported).

- Failure is Hermes' own verdict (`bridge.failed`, constraint 2), never a parse of the result.
- The card goes in as a `unblockbruecke_card` key of a JSON object result, or as one bracketed line
  after a plain-text result; any other shape is left alone (constraint 1, U4), so Hermes still
  counts the call as failed and its own guardrail still fires on it.
- Only cards tagged `auto` from decks whose Hermes switch is on (AX-6). A card whose tags fit the kind
  of failure is preferred (AX-3, M0 P5: for an unreachable upstream the `reframe` cards); the kind is
  read from the error text only to choose among `auto` cards, never to decide whether the call failed.
- What the agent reads is short (AX-7): the card, one sentence, the `draw_id`.
- State is an in-memory LRU of the last 512 turn ids behind a lock; a call without a `turn_id`
  (Hermes sets one on every agent turn; execute_code's inner calls have none) is skipped. Parallel
  tool batches count in completion order, and the slot for a card is reserved under the lock, so N
  concurrent failures give exactly one card (constraint 3).
- The hook is fail-open: any exception returns None (no change) (constraint 4).
- With nobody at the keyboard, cards tagged `human` are left out (constraint 6).
- The journal gets the draw with where the turn ran, and for the next call of the same turn its
  status as a fact (`next_call`), plus the calls the turn needed until one worked (F10). Tool arguments
  are never logged. The draw row's `attached` means offered: this hook returned the result with the
  card. Hermes keeps the first string any `transform_tool_result` hook returns, so when another
  plugin's hook answers first the card does not reach the model although the row says attached.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from . import bridge, draw as draw_mod, journal, service

logger = logging.getLogger(__name__)

KEY = "unblockbruecke_card"
LRU_SIZE = 512
EXTRA = 2  # the window holds threshold + EXTRA calls: 3 of the last 5 by default (D16)
NOTE = "{n} of your last {w} calls failed; this call still failed. A nudge, not an order."

# The kind of failure, read from the error text, and the tags of `auto` cards that suit it (M0 P5
# measured one row: an unreachable upstream and the `reframe` cards; a deck's glossary defines its tags).
KINDS: list[tuple[str, re.Pattern, tuple]] = [
    ("unreachable", re.compile(r"(?i)time[sd]?[ -]?out|timed out|unreachable|connection (?:refused|reset|aborted)|"
                               r"econnrefused|etimedout|could not resolve|name resolution|temporar(?:y|ily) "
                               r"(?:failure|unavailable)|service unavailable|bad gateway|\b50[234]\b"), ("reframe",)),
]
TEXT_SCAN = 4000  # characters of the result read for the kind


@dataclass
class TurnState:
    window: deque = field(default_factory=deque)  # True per failed call, newest last
    cards: int = 0
    pending: list = field(default_factory=list)  # [{"draw_id", "calls": n, "recovered": bool}]


class Tracker:
    """Per-turn windows, an LRU of `size` turn keys, one lock."""

    def __init__(self, size: int = LRU_SIZE):
        self.size = size
        self.turns: "OrderedDict[str, TurnState]" = OrderedDict()
        self.lock = threading.Lock()

    def step(self, key: str, failed: bool, threshold: int) -> tuple[bool, int, list]:
        """Count one call. Returns (draw now?, failed calls in the window at this call, outcome lines)."""
        with self.lock:
            state = self.turns.get(key)
            if state is None:
                state = self.turns[key] = TurnState()
                while len(self.turns) > self.size:
                    self.turns.popitem(last=False)
            else:
                self.turns.move_to_end(key)
            outcomes = []
            for p in state.pending:
                p["calls"] += 1
                if p["calls"] == 1:
                    outcomes.append((p["draw_id"], {"status": "failed" if failed else "ok"}))
                if not failed and not p["recovered"]:
                    p["recovered"] = True
                    outcomes.append((p["draw_id"], {"calls_to_recover": p["calls"]}))
            state.pending = [p for p in state.pending if not p["recovered"]]
            state.window.append(bool(failed))
            while len(state.window) > threshold + EXTRA:
                state.window.popleft()
            count = sum(state.window)
            fire = failed and count >= threshold and state.cards < 1
            if fire:
                state.cards += 1  # one card per turn: the slot is taken under the lock
            return fire, count, outcomes

    def note_draw(self, key: str, draw_id: str) -> None:
        with self.lock:
            state = self.turns.get(key)
            if state is not None:
                state.pending.append({"draw_id": draw_id, "calls": 0, "recovered": False})


def failure_kind(result: Any) -> tuple[str, tuple]:
    """(kind, preferred tags) for a failed result, or ("", ()) when no kind fits."""
    if isinstance(result, (dict, list)):
        try:
            result = json.dumps(result, ensure_ascii=False)
        except (TypeError, ValueError):
            return "", ()
    if not isinstance(result, str):
        return "", ()
    text = result[:TEXT_SCAN]
    for kind, pattern, tags in KINDS:
        if pattern.search(text):
            return kind, tags
    return "", ()


def note(count: int, threshold: int) -> str:
    return NOTE.format(n=count, w=threshold + EXTRA)


def attach(result: Any, card: dict, count: int, draw_id: str = "", threshold: int = 3) -> Optional[str]:
    """The result with the card added, or None when its shape takes no card (constraint 1). About 300
    characters: the agent face, one sentence, the `draw_id` to rate it when the user says it helped."""
    if not isinstance(result, str):
        return None
    sentence = note(count, threshold)
    payload = {"card": card["agent"], "note": sentence}
    if draw_id:
        payload["draw_id"] = draw_id
    stripped = result.strip()
    if stripped.startswith("{"):
        try:
            data = json.loads(stripped)
        except ValueError:
            data = None
        if isinstance(data, dict):
            if KEY in data:
                return None
            data[KEY] = payload
            return json.dumps(data, ensure_ascii=False)
        return None  # JSON-looking text that is not an object: appended prose could change the verdict
    if stripped.startswith("["):
        return None
    rate = f" draw_id {draw_id}" if draw_id else ""
    line = f"[unblockbruecke] {card['agent']} ({sentence}{rate})"
    return result.rstrip("\n") + "\n\n" + line


class AutoDraw:
    """The hook object: settings and the store come from callables so a reload is never needed."""

    def __init__(self, store_factory: Callable[[], Any], read_settings: Callable[[], dict],
                 unattended: Callable[[], Optional[str]], tracker: Optional[Tracker] = None,
                 autodraw_on: Optional[Callable[[], bool]] = None,
                 where: Optional[Callable[[], tuple]] = None):
        self.store_factory = store_factory
        self.read_settings = read_settings
        self.unattended = unattended
        self.tracker = tracker or Tracker()
        # Every tool call of the profile passes here: read the one `autodraw` setting first, and the
        # rest only when it is on (under plugins.isolation: host each read is a round trip).
        self.autodraw_on = autodraw_on or (lambda: bool(self.read_settings().get("autodraw")))
        self.where = where or (lambda: ("unknown", ""))
        self.last_ms = 0.0
        self.drawn: "OrderedDict[str, dict]" = OrderedDict()  # turn_id -> the card it got (the reply line)
        self.drawn_lock = threading.Lock()

    def __call__(self, tool_name: str = "", result: Any = None, status: str = "", turn_id: str = "",
                 session_id: str = "", **_kw: Any) -> Optional[str]:
        try:
            return self._run(tool_name, result, status, turn_id, session_id)
        except Exception:
            logger.debug("unblockbruecke: auto-draw hook failed open", exc_info=True)
            return None

    def _run(self, tool: str, result: Any, status: str, turn_id: str, session_id: str) -> Optional[str]:
        if not turn_id or tool == "unblockbruecke_card" or not self.autodraw_on():
            return None
        settings = self.read_settings()
        if not settings.get("autodraw"):
            return None
        key = turn_id  # per turn only (D17 not supported by M0 P1)
        threshold = settings["autodraw_threshold"]
        failed = bridge.failed(tool, result, status)
        fire, count, outcomes = self.tracker.step(key, failed, threshold)
        store = None
        for draw_id, next_ in outcomes:
            store = store or self.store_factory()
            if "status" in next_:
                next_ = {**next_, "tool": tool}
            journal.record_outcome(store, draw_id, next_)
        if not fire:
            return None
        started = time.perf_counter()
        store = store or self.store_factory()
        reason = self.unattended()
        _kind, prefer = failure_kind(result)
        where, platform = self._where()
        try:
            picked = service.draw_card(store, settings, context="auto", by="auto", unattended=bool(reason),
                                       record=False, prefer=list(prefer))
        except (draw_mod.NoCard, LookupError) as exc:
            journal.append(store, {"kind": "skipped", "at": bridge.iso(), "session_id": session_id,
                                   "turn_id": turn_id, "tool": tool, "streak": count, "where": where,
                                   "reason": "unattended" if reason else "no_card", "detail": str(exc)[:200]})
            return None
        card = picked["card"]
        offered = attach(result, card, count, threshold=threshold) is not None  # does this shape take a card?
        row = journal.record_draw(store, by="auto", deck=card["deck"], card=card["id"], face="agent",
                                  context="auto", session_id=session_id, turn_id=turn_id, tool=tool,
                                  streak=count, attached=offered, where=where, platform=platform)
        new = attach(result, card, count, row["draw_id"], threshold) if offered else None
        self.tracker.note_draw(key, row["draw_id"])
        if new is not None:
            self._remember(turn_id, card)
        self.last_ms = (time.perf_counter() - started) * 1000
        return new

    def _where(self) -> tuple[str, str]:
        try:
            code, platform = self.where()
            return str(code or "unknown"), str(platform or "")
        except Exception:
            return "unknown", ""

    def _remember(self, turn_id: str, card: dict) -> None:
        with self.drawn_lock:
            self.drawn[turn_id] = {"deck": card["deck"], "id": card["id"], "human": card["human"]}
            while len(self.drawn) > LRU_SIZE:
                self.drawn.popitem(last=False)

    def card_for_turn(self, turn_id: str) -> Optional[dict]:
        """The card this hook attached in a turn, once (the reply line takes it), or None."""
        if not turn_id:
            return None
        with self.drawn_lock:
            return self.drawn.pop(turn_id, None)
