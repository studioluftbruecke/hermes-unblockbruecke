"""`/card [deck|agent]` in every chat surface (F4).

`/card` draws a human card from the decks switched on, `/card coding` from one deck, `/card agent`
from Agent unblock with both faces. Plain text only, so it reads the same on every surface; the
Desktop renders `::card{...}` lines the agent writes, not this command's text.
"""
from __future__ import annotations

from typing import Any, Callable

from . import decks as decks_mod, draw as draw_mod, service

HELP = ("/card draws a card. /card <deck> draws from one deck (for example /card coding), /card agent shows "
        "an Agent unblock card with both faces, /card decks lists the decks.")


def render(card: dict, both: bool = False) -> str:
    lines = [f"{card['deck_name']} · {card['id']}", card["human"]]
    if both or card["face"] == "agent":
        lines.append(f"For an agent: {card['agent']}")
    return "\n".join(lines)


def run(raw: str, store: Any, settings: dict, session_id: str = "") -> str:
    arg = (raw or "").strip().lower()
    if arg in ("help", "?"):
        return HELP
    cat = decks_mod.catalog(store)
    if arg == "decks":
        rows = [decks_mod.deck_summary(d) for d in cat["decks"].values() if not d.get("shadowed_by")]
        return "Decks: " + ", ".join(f"{r['deck']} ({r['cards']})" + ("" if r["switch"]["draw"] else " off")
                                     for r in sorted(rows, key=lambda r: r["deck"]))
    both = arg == "agent"
    deck = service.AGENT_DECK if both else (arg or None)
    try:
        out = service.draw_card(store, settings, deck=deck, context="any", by="user", session_id=session_id,
                                face="agent" if both else "human", cat=cat)
    except LookupError as exc:
        return f"{exc}. {HELP}"
    except draw_mod.NoCard as exc:
        return f"No card to draw: {exc}."
    return render(out["card"], both=both)


def make_handler(store_factory: Callable[[], Any], settings_factory: Callable[[], dict]):
    def handler(raw_args: str = "", session_id: str = "", **_ignored: Any) -> str:
        try:
            return run(raw_args, store_factory(), settings_factory(), session_id=session_id or "")
        except Exception as exc:  # a slash command never shows a traceback
            return f"Unblockbrücke could not draw: {type(exc).__name__}: {exc}"

    return handler
