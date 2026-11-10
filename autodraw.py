"""Auto-draw (F6, F7): the `transform_tool_result` hook.

When the setting `autodraw` is on and a turn's tool calls fail `autodraw_threshold` times in a row
(any tools; a success resets the streak), the failing result that reaches the threshold carries one
card, at most `autodraw_per_turn` per turn.

- Failure is Hermes' own verdict (`bridge.failed`, constraint 2), never a parse of the result.
- The card goes in as a `unblockbruecke_card` key of a JSON object result, or as one bracketed line
  after a plain-text result; any other shape is left alone (constraint 1, U4), so Hermes still
  counts the call as failed and its own guardrail still fires on it.
- State is an in-memory LRU of the last 512 turn ids behind a lock; a call without a `turn_id`
  (Hermes sets one on every agent turn; execute_code's inner calls have none) is skipped. Parallel
  tool batches count in completion order, and the slot for a card is reserved under the lock, so N
  concurrent failures give exactly one card (constraint 3).
- The hook is fail-open: any exception returns None (no change) (constraint 4).
- With nobody at the keyboard, cards tagged `human` are left out (constraint 6).
- The journal gets the draw and, for the next calls of the same turn, the next call's status and the
  number of calls the turn needed to recover (F10). Tool arguments are never logged. The draw row's
  `attached` means offered: this hook returned the result with the card. Hermes keeps the first
  string any `transform_tool_result` hook returns, so when another plugin's hook answers first the
  card does not reach the model although the row says attached, and the turn's slot is used.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from . import bridge, draw as draw_mod, journal, service

logger = logging.getLogger(__name__)

KEY = "unblockbruecke_card"
LRU_SIZE = 512
WHY = ("UnblockBrücke drew this card because {n} tool calls failed in a row in this turn. The call above still "
       "failed; read its error as usual. The card is a lateral prompt, not an order: use its direction for the "
       "next step if it fits.")


@dataclass
class TurnState:
    streak: int = 0
    cards: int = 0
    pending: list = field(default_factory=list)  # [{"draw_id", "calls": n, "recovered": bool}]


class Tracker:
    """Per-turn streaks, an LRU of `size` turn keys, one lock."""

    def __init__(self, size: int = LRU_SIZE):
        self.size = size
        self.turns: "OrderedDict[str, TurnState]" = OrderedDict()
        self.lock = threading.Lock()

    def step(self, key: str, failed: bool, threshold: int, per_turn: int) -> tuple[bool, int, list]:
        """Count one call. Returns (draw now?, streak at this call, outcome lines to write)."""
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
            state.streak = state.streak + 1 if failed else 0
            streak = state.streak
            fire = failed and streak >= threshold and state.cards < per_turn
            if fire:
                state.cards += 1
                state.streak = 0  # the next card needs another full streak
            return fire, streak, outcomes

    def note_draw(self, key: str, draw_id: str) -> None:
        with self.lock:
            state = self.turns.get(key)
            if state is not None:
                state.pending.append({"draw_id": draw_id, "calls": 0, "recovered": False})


def attach(result: Any, card: dict, streak: int, draw_id: str = "") -> Optional[str]:
    """The result with the card added, or None when its shape takes no card (constraint 1). The card
    names its `draw_id` so the agent can rate it when the user says it helped."""
    if not isinstance(result, str):
        return None
    payload = {"deck": card["deck"], "deck_name": card["deck_name"], "id": card["id"], "card": card["agent"],
               "human": card["human"], "why": WHY.format(n=streak)}
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
    rate = f"; draw_id {draw_id}" if draw_id else ""
    line = (f"[unblockbruecke] {streak} failed calls in a row this turn. Card {card['id']} ({card['deck_name']}): "
            f"{card['agent']} (A lateral prompt, not an order{rate}.)")
    return result.rstrip("\n") + "\n\n" + line


class AutoDraw:
    """The hook object: settings and the store come from callables so a reload is never needed."""

    def __init__(self, store_factory: Callable[[], Any], read_settings: Callable[[], dict],
                 unattended: Callable[[], Optional[str]], tracker: Optional[Tracker] = None,
                 autodraw_on: Optional[Callable[[], bool]] = None):
        self.store_factory = store_factory
        self.read_settings = read_settings
        self.unattended = unattended
        self.tracker = tracker or Tracker()
        # Every tool call of the profile passes here: read the one `autodraw` setting first, and the
        # rest only when it is on (under plugins.isolation: host each read is a round trip).
        self.autodraw_on = autodraw_on or (lambda: bool(self.read_settings().get("autodraw")))
        self.last_ms = 0.0

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
        key = turn_id  # per turn only: a session-wide key would spend the per-turn budget once for good
        failed = bridge.failed(tool, result, status)
        fire, streak, outcomes = self.tracker.step(key, failed, settings["autodraw_threshold"],
                                                   settings["autodraw_per_turn"])
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
        try:
            picked = service.draw_card(store, settings, context="auto", by="auto", unattended=bool(reason),
                                       record=False)
        except (draw_mod.NoCard, LookupError) as exc:
            journal.append(store, {"kind": "skipped", "at": bridge.iso(), "session_id": session_id,
                                   "turn_id": turn_id, "tool": tool, "streak": streak,
                                   "reason": "unattended" if reason else "no_card", "detail": str(exc)[:200]})
            return None
        card = picked["card"]
        offered = attach(result, card, streak) is not None  # does this result shape take a card?
        row = journal.record_draw(store, by="auto", deck=card["deck"], card=card["id"], face="agent",
                                  context="auto", session_id=session_id, turn_id=turn_id, tool=tool,
                                  streak=streak, attached=offered)
        new = attach(result, card, streak, row["draw_id"]) if offered else None
        self.tracker.note_draw(key, row["draw_id"])
        self.last_ms = (time.perf_counter() - started) * 1000
        return new
