"""One way to draw, used by the agent tool, `/card`, the routes and auto-draw.

`draw_card()` picks the decks for a request, applies the journal's weights (setting `learning`),
leaves out recent repeats, draws, and writes the journal line. Every caller gets the same shape:
{"draw_id", "card": draw.card_view(...)}.
"""
from __future__ import annotations

from typing import Any, Optional

from . import bridge, decks as decks_mod, draw as draw_mod, journal
from .store import Store

AGENT_DECK = "agent-unblock"
HUMAN_DECK = "human-unblock"
ECHO_CHARS = 40  # an unknown name is echoed at most this long
ECHO_NAMES = 5  # and at most this many of them


def echo(names: Any) -> str:
    """Names for a message, cut short: at most ECHO_NAMES, each at most ECHO_CHARS characters."""
    items = [names] if isinstance(names, str) else [str(n) for n in names]
    shown = [n if len(n) <= ECHO_CHARS else n[:ECHO_CHARS] + "..." for n in items[:ECHO_NAMES]]
    more = len(items) - len(shown)
    return ", ".join(shown) + (f" and {more} more" if more > 0 else "")


def as_names(value: Any, what: str) -> Optional[list]:
    """A list-of-names argument: None or "" is none, one string is one name, a list must hold strings.
    Any other type raises ValueError (the routes answer 400 invalid, the tools `invalid`)."""
    if value is None or value == "":
        return None
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)) and all(isinstance(v, str) for v in value):
        return [v for v in value if v] or None
    raise ValueError(f"{what} must be a name or a list of names")


def pick_decks(cat: dict, settings: dict, deck: Optional[str] = None, decks: Optional[list] = None,
               context: str = "any") -> list[dict]:
    if deck is not None and not isinstance(deck, str):
        raise ValueError("deck must be a deck name")
    names = ([deck] if deck else []) + (as_names(decks, "decks") or [])
    if names:
        found = decks_mod.drawable(cat, names)
        missing = [n for n in names if decks_mod.resolve(cat, n) is None]
        if missing:
            known = ", ".join(sorted(s for s, d in cat["decks"].items() if not d.get("shadowed_by")))
            raise LookupError(f"no deck named {echo(missing)}; decks: {known}")
        return found
    if context == "auto":
        # Each deck's Hermes switch decides (seeded once from a stored autodraw_decks).
        return decks_mod.hermes_decks(cat)
    on = decks_mod.drawable(cat)
    preferred = {"break": HUMAN_DECK, "human": HUMAN_DECK, "stuck": AGENT_DECK}.get(context)
    if preferred:
        chosen = [d for d in on if d["deck"] in (preferred, preferred + decks_mod.OWN_SUFFIX)]
        if chosen:
            return chosen
    return on


def ensure_seed(store: Store, settings: dict) -> None:
    """The one-time seed of the Hermes switches from 0.1's `autodraw_decks` (see decks.seed_hermes_switches).
    Cheap after the first call: one read of the switches file."""
    decks_mod.seed_hermes_switches(store, settings.get("autodraw_decks", [AGENT_DECK]))


def hermes_example(store: Store, cat: Optional[dict] = None) -> Optional[dict]:
    """The example card under the Hermes switch: today's `auto` card of the first deck Hermes draws from
    (else the Agent deck), the same all day. None when no deck has an `auto` card."""
    cat = cat or decks_mod.catalog(store)
    decks = sorted(decks_mod.hermes_decks(cat), key=lambda d: (d["deck"] != AGENT_DECK, d["deck"]))
    agent = decks_mod.resolve(cat, AGENT_DECK)
    for deck in decks + ([agent] if agent else []):
        cards = [c for c in deck.get("cards") or [] if "auto" in c["tags"]]
        if cards:
            picked = draw_mod.card_of_day({**deck, "cards": cards}, bridge.today(), salt="hermes")
            return draw_mod.card_view(deck, picked["card"], "agent")
    return None


def learned_weights(store: Store, settings: dict, all_rows: Optional[list] = None) -> dict:
    if not settings.get("learning", True):
        return {}
    all_rows = journal.rows(store) if all_rows is None else all_rows
    return journal.weights(journal.stats_from(journal.since_reset(all_rows)))


def draw_card(store: Store, settings: dict, *, deck: Optional[str] = None, decks: Optional[list] = None,
              context: str = "any", tags: Optional[list] = None, by: str = "user", unattended: bool = False,
              session_id: str = "", turn_id: str = "", tool: str = "", streak: Optional[int] = None,
              attached: Optional[bool] = None, face: Optional[str] = None, record: bool = True,
              rng: Any = None, cat: Optional[dict] = None, prefer: Optional[list] = None, where: str = "",
              platform: str = "") -> dict:
    ensure_seed(store, settings)
    cat = cat or decks_mod.catalog(store)
    tags = as_names(tags, "tags")
    chosen = pick_decks(cat, settings, deck, decks, context)
    all_rows = journal.rows(store)  # read once: recent draws and weights both come from it
    picked = draw_mod.draw(chosen, context=context, tags=tags, unattended=unattended,
                           recent=journal.recent_from(all_rows), weights=learned_weights(store, settings, all_rows),
                           rng=rng, prefer=prefer)
    face = face if face in ("human", "agent") else picked["face"]
    view = draw_mod.card_view(picked["deck"], picked["card"], face)
    out: dict = {"card": view}
    if record:
        row = journal.record_draw(store, by=by, deck=view["deck"], card=view["id"], face=face, context=context,
                                  session_id=session_id, turn_id=turn_id, tool=tool, streak=streak, attached=attached,
                                  where=where, platform=platform)
        out["draw_id"] = row["draw_id"]
    return out


def card_of_day(store: Store, settings: dict, cat: Optional[dict] = None) -> Optional[dict]:
    """Today's human card (Hermes' zone), or None when the setting is off or no deck can give one."""
    if not settings.get("card_of_day", True):
        return None
    cat = cat or decks_mod.catalog(store)
    deck = decks_mod.resolve(cat, HUMAN_DECK)
    if deck is None or not deck["switch"]["draw"]:
        on = [d for d in decks_mod.drawable(cat) if d.get("cards")]
        if not on:
            return None
        deck = on[0]
    picked = draw_mod.card_of_day(deck, bridge.today())
    return {"date": bridge.today().isoformat(), "card": draw_mod.card_view(deck, picked["card"], "human")}


def show(store: Store, deck: str, card_id: str, cat: Optional[dict] = None) -> dict:
    cat = cat or decks_mod.catalog(store)
    found = decks_mod.resolve(cat, deck) or cat["decks"].get(deck)
    if found is None:
        raise LookupError(f"no deck named {echo(deck)}")
    card = decks_mod.find_card(found, card_id)
    if card is None and found.get("copy_of"):
        original = cat["decks"].get(found["copy_of"])
        card = decks_mod.find_card(original, card_id) if original else None
    if card is None:
        raise LookupError(f"deck {found['deck']} has no card {echo(card_id)}")
    return draw_mod.card_view(found, card, "human")
