"""Drawing a card.

`draw()` picks one card from a set of decks: context filters first, then the last three draws of
each deck are left out (when the deck has more cards than that), then a weighted pick where a
card's weight comes from the journal (`learning` off means all weights 1). The random source
is injectable so tests are seeded.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import random
from collections import Counter
from typing import Any, Optional

CONTEXTS = ("stuck", "break", "human", "any", "auto")
HUMAN_FACE_CONTEXTS = ("break", "human", "any", "day")
NO_REPEAT = 3

_SYSTEM = random.SystemRandom()


class NoCard(Exception):
    """No card fits: every deck is off, empty after filters, or unknown."""


def face_for(context: str) -> str:
    return "human" if context in HUMAN_FACE_CONTEXTS else "agent"


def candidates(decks: list[dict], context: str = "any", tags: Optional[list] = None,
               unattended: bool = False) -> list[tuple[dict, dict]]:
    """(deck, card) pairs a draw may return, before repeats and weights."""
    wanted = {t for t in (tags or []) if isinstance(t, str) and t}
    out: list[tuple[dict, dict]] = []
    for deck in decks:
        for card in deck.get("cards") or []:
            ctags = set(card.get("tags") or [])
            if wanted and not (wanted & ctags):
                continue
            if unattended and "human" in ctags:
                continue  # no card that asks a person when nobody is there
            out.append((deck, card))
    if context == "auto":  # only cards written for Hermes, never a person's card as a fallback
        out = [(d, c) for d, c in out if "auto" in (c.get("tags") or [])]
    return out


def key(deck: dict, card: dict) -> str:
    return f"{deck['deck']}/{card['id']}"


def draw(decks: list[dict], context: str = "any", tags: Optional[list] = None, unattended: bool = False,
         recent: Optional[dict] = None, weights: Optional[dict] = None, rng: Any = None,
         prefer: Optional[list] = None) -> dict:
    """One card: {"deck": <deck>, "card": <card>, "face": "human"|"agent"}.

    `recent` maps a deck slug to its recently drawn card ids, newest first; `weights` maps
    "deck/id" to a positive weight. `prefer` names tags that fit the moment (auto-draw: the kind of
    failure): when a card carries one, the pick is among those, before the repeat rule. A
    matched pool is small (three `reframe` cards in the Agent deck), so there the repeat rule leaves
    out at most all but one of them: the match wins over variety (otherwise three quick matched draws in a
    row push the fourth off the match)."""
    if context not in CONTEXTS:
        raise ValueError(f"context must be one of {', '.join(CONTEXTS)}")
    pool = candidates(decks, context, tags, unattended)
    if not pool:
        raise NoCard("no card fits: the decks are switched off, empty, or no card has those tags")
    wanted = {t for t in (prefer or []) if isinstance(t, str)}
    matched = [(d, c) for d, c in pool if wanted & set(c.get("tags") or [])] if wanted else []
    pool = matched or pool
    recent = recent or {}
    sizes = Counter(id(d) for d, _ in pool)  # once per draw: counting per card made a draw quadratic
    skips: dict[int, set] = {}
    fresh = []
    for deck, card in pool:
        skip = skips.get(id(deck))
        if skip is None:
            size = sizes[id(deck)]
            keep_out = NO_REPEAT if size > NO_REPEAT else (size - 1 if matched else 0)
            skip = skips[id(deck)] = set(list(recent.get(deck["deck"]) or [])[:keep_out])
        if card["id"] in skip:
            continue
        fresh.append((deck, card))
    pool = fresh or pool
    w = [max(0.0001, float((weights or {}).get(key(d, c), 1.0))) for d, c in pool]
    rng = rng or _SYSTEM
    deck, card = rng.choices(pool, weights=w, k=1)[0]
    return {"deck": deck, "card": card, "face": face_for(context)}


def card_of_day(deck: dict, day: dt.date, salt: str = "") -> dict:
    """The same human card all day: a hash of the date picks it (the date is in Hermes' zone)."""
    cards = [c for c in deck.get("cards") or []]
    if not cards:
        raise NoCard(f"deck {deck.get('deck')} has no cards")
    digest = hashlib.sha256(f"{day.isoformat()}:{deck['deck']}:{salt}".encode()).digest()
    card = cards[int.from_bytes(digest[:8], "big") % len(cards)]
    return {"deck": deck, "card": card, "face": "human"}


def card_view(deck: dict, card: dict, face: str = "human") -> dict:
    """The JSON shape of one card everywhere (tool, routes, command)."""
    from .decks import explain_tags

    return {"deck": deck["deck"], "deck_name": deck.get("name", deck["deck"]), "mark": deck.get("mark", "square"),
            "id": card["id"], "human": card["human"], "agent": card["agent"], "tags": list(card.get("tags") or []),
            "face": face, "why": explain_tags(deck, list(card.get("tags") or [])),
            "directive": f'::card{{deck="{deck["deck"]}" id="{card["id"]}"}}'}
