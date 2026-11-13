"""`unblockbruecke_card`: draw a card, list decks, show one card, read the journal, rate a draw (F5).

`draw` with `context: "break"` is Eselsbrücke's break contract (PLAN constraint 12, R26 there): the
answer always carries string `title` (the human face) and `text` (the agent face), plus our fields.
"""
from __future__ import annotations

from typing import Any

from .. import decks as decks_mod, draw as draw_mod, journal, service

ACTIONS = ("draw", "decks", "show", "journal", "rate")

SCHEMA = {
    "name": "unblockbruecke_card",
    "description": (
        "draw a card when you or the user are stuck; also decks, show, journal, rate. "
        "Unblockbrücke: short two-faced cards to unblock people and agents. A card is a nudge, never an order. "
        "draw gives one card: context stuck is for you, the agent, when your approach keeps failing (agent face); "
        "human or break is for the user (human face); any. "
        "Optional deck, e.g. agent-unblock, human-unblock, coding, design, shaders, writing. "
        "decks lists the decks with their switches. show gives one card by deck and id. "
        "journal gives recent draws and per-card stats. rate marks a draw helped or not_now when the user says so. "
        "Draw when the user asks for a card or says they are stuck. "
        "Show a card in the reply with the directive line the answer gives you. "
        "Guide: skill unblockbruecke:unblockbruecke."),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": list(ACTIONS)},
            "deck": {"type": "string", "description": "Deck slug for draw or show (see action decks)."},
            "decks": {"type": "array", "items": {"type": "string"}, "description": "Draw from several decks."},
            "context": {"type": "string", "enum": list(draw_mod.CONTEXTS[:4]),
                        "description": "draw: stuck (agent face, for you), human, break, any (human face)."},
            "tags": {"type": "array", "items": {"type": "string"}, "description": "draw: only cards with one of these tags."},
            "id": {"type": "string", "description": "show: card id like ag-03."},
            "limit": {"type": "integer", "description": "journal: how many draws (default 10, at most 50)."},
            "draw_id": {"type": "string", "description": "rate: the draw_id a draw answered."},
            "rating": {"type": "string", "enum": list(journal.RATINGS)},
        },
        "required": ["action"],
    },
}


def handle(args: dict, rt) -> dict:
    action = args.get("action")
    if action not in ACTIONS:
        return {"ok": False, "error": "unknown_action", "message": f"action must be one of {', '.join(ACTIONS)}"}
    return globals()[f"_{action}"](args, rt)


def _draw(args: dict, rt) -> dict:
    context = args.get("context") or "any"
    if context not in draw_mod.CONTEXTS[:4]:
        return {"ok": False, "error": "invalid", "message": "context must be stuck, human, break or any"}
    reason = rt.unattended()
    # Only a card the agent takes for itself (stuck) must not ask a person who is not there (F7);
    # a card drawn for a person (human, break, any) is read by that person later.
    skip_human = bool(reason) and context == "stuck"
    where, platform = rt.where() if rt.author == "agent" else ("", "")
    try:
        out = service.draw_card(rt.store, rt.settings, deck=args.get("deck") or None, decks=args.get("decks") or None,
                                context=context, tags=args.get("tags") or None, by=rt.author,
                                unattended=skip_human, session_id=rt.session_id, where=where, platform=platform)
    except LookupError as exc:
        return {"ok": False, "error": "unknown_deck", "message": str(exc)}
    except ValueError as exc:  # a wrong argument type (deck, decks, tags)
        return {"ok": False, "error": "invalid", "message": str(exc)}
    except draw_mod.NoCard as exc:
        extra = f" Cards that ask a person were left out because nobody is at the keyboard ({reason})." if skip_human else ""
        return {"ok": False, "error": "no_card", "message": f"{exc}.{extra}"}
    card = out["card"]
    answer = {"ok": True, "draw_id": out["draw_id"], "card": card,
              "title": card["human"], "text": card["agent"],
              "deck": card["deck"], "face": card["face"],
              "note": "A lateral prompt, not an order: use it if it fits, say so if it does not."}
    if skip_human:
        answer["unattended"] = f"No cards that ask a person were drawn ({reason})."
    return answer


def _decks(args: dict, rt) -> dict:
    cat = decks_mod.catalog(rt.store)
    rows = [decks_mod.deck_summary(d) for d in sorted(cat["decks"].values(), key=lambda d: d["deck"])]
    out = {"ok": True, "decks": rows, "autodraw": {"on": rt.settings.get("autodraw", False),
                                                   "decks": [d["deck"] for d in decks_mod.hermes_decks(cat)]}}
    if cat["broken"]:
        out["broken"] = cat["broken"]
    return out


def _show(args: dict, rt) -> dict:
    deck, cid = args.get("deck"), args.get("id")
    if (deck is not None and not isinstance(deck, str)) or (cid is not None and not isinstance(cid, str)):
        return {"ok": False, "error": "invalid", "message": "show takes deck and id as text (e.g. agent-unblock, ag-03)"}
    if not deck or not cid:
        if isinstance(cid, str) and "-" in cid and not deck:
            deck = _deck_for_prefix(rt, cid.split("-")[0])
        if not deck or not cid:
            return {"ok": False, "error": "invalid", "message": "show needs deck and id (e.g. agent-unblock, ag-03)"}
    try:
        return {"ok": True, "card": service.show(rt.store, deck, cid)}
    except LookupError as exc:
        return {"ok": False, "error": "unknown_card", "message": str(exc)}


def _deck_for_prefix(rt, prefix: str) -> Any:
    for slug, deck in decks_mod.catalog(rt.store)["decks"].items():
        if deck.get("prefix") == prefix and not deck.get("shadowed_by"):
            return slug
    return None


def _journal(args: dict, rt) -> dict:
    try:
        limit = max(1, min(50, int(args.get("limit") or 10)))
    except (TypeError, ValueError, OverflowError):
        limit = 10
    rows = journal.draws(rt.store, limit=limit)
    stats = journal.stats(rt.store)
    top = sorted(((k, s) for k, s in stats.items() if s["helped"]), key=lambda kv: -kv[1]["helped"])[:5]
    return {"ok": True, "draws": rows, "helped_most": [{"card": k, **s} for k, s in top],
            "totals": {"draws": sum(s["drawn"] for s in stats.values()),
                       "helped": sum(s["helped"] for s in stats.values()),
                       "by_auto": sum(s["by_auto"] for s in stats.values())}}


def _rate(args: dict, rt) -> dict:
    reason = rt.unattended()
    if reason:
        return {"ok": False, "error": "unattended",
                "message": f"Refused: rating a draw records the user's judgement, and this run has no person at the "
                           f"keyboard ({reason}). Nothing was changed."}
    try:
        row = journal.rate(rt.store, str(args.get("draw_id") or ""), str(args.get("rating") or ""), by=rt.author)
    except (LookupError, ValueError) as exc:
        return {"ok": False, "error": "invalid", "message": str(exc)}
    return {"ok": True, "rated": {"draw_id": row["draw_id"], "rating": row["rating"]}}
