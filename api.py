"""The routes' logic, without FastAPI, so tests call it directly: each function returns (status, body).

`dashboard/plugin_api.py` only adapts these to FastAPI. Every body carries `schema`; errors are
`{ok: false, schema, error, message, problems?}` (contract §5). These are the user's own clicks
(author `user`), so no unattended check runs here; for every profile except the dashboard's own,
routes run in the profile's plugin host child. Writes take an optional `op_id`: a repeat answers
`duplicate: true` and changes nothing.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Callable, Optional

from . import bridge, decks as decks_mod, draw as draw_mod, editor, journal, service, settings as settings_mod
from .store import Store, StoreError, default_root

SCHEMA = 1
OPS_FILE = "ops.json"
OPS_KEEP = 200
OP_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")
log = logging.getLogger(__name__)


def _version() -> str:
    text = (Path(__file__).resolve().parent / "plugin.yaml").read_text(encoding="utf-8")
    found = re.search(r'(?m)^version:\s*"?([^"\n]+)"?', text)
    return found.group(1) if found else "?"


VERSION = _version()

# Tests point these at a temp folder and fixed settings; in Hermes they follow the bound home per call.
_store_factory: Callable[[], Store] = lambda: Store(lambda: default_root())  # noqa: E731
_settings_factory: Callable[[], dict] = settings_mod.load_route_settings


def configure(store_factory: Optional[Callable[[], Store]] = None,
              settings_factory: Optional[Callable[[], dict]] = None) -> None:
    global _store_factory, _settings_factory
    _store_factory = store_factory or (lambda: Store(lambda: default_root()))
    _settings_factory = settings_factory or settings_mod.load_route_settings


def store() -> Store:
    return _store_factory()


def ok(body: dict, status: int = 200) -> "tuple[int, dict]":
    return status, {"ok": True, "schema": SCHEMA, **body}


def fail(status: int, code: str, message: str, **extra: Any) -> "tuple[int, dict]":
    return status, {"ok": False, "schema": SCHEMA, "error": code, "message": message, **extra}


STATUS = {"invalid": 400, "unknown_deck": 404, "unknown_card": 404, "unknown_version": 404, "unknown_draw": 404,
          "stale_preview": 409, "exists": 409, "invalid_deck": 422, "bad_yaml": 422, "too_large": 422}


def _guard(fn):
    def wrapped(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except editor.EditError as exc:
            extra = {k: v for k, v in exc.extra.items() if k in ("problems", "problems_more", "preview")}
            return fail(STATUS.get(exc.code, 400), exc.code, str(exc), **extra)
        except decks_mod.DeckError as exc:
            return fail(STATUS.get(exc.code, 422), exc.code, str(exc), **decks_mod.problem_fields(exc.problems))
        except draw_mod.NoCard as exc:
            return fail(409, "no_card", str(exc))
        except LookupError as exc:
            return fail(404, "unknown_deck", str(exc).strip("'\""))
        except StoreError as exc:
            return fail(500, "store", str(exc))
        except OverflowError:
            return fail(400, "invalid", WRONG_TYPE)
        except ValueError as exc:
            return fail(400, "invalid", str(exc))
        except (TypeError, AttributeError) as exc:
            # The last line of defence: a field of the wrong type reached code that expected another.
            # The message names no internals; the log keeps the exception for whoever debugs it.
            log.info("unblockbruecke route %s refused a wrong type: %r", fn.__name__, exc)
            return fail(400, "invalid", WRONG_TYPE)
    wrapped.__name__ = fn.__name__
    return wrapped


WRONG_TYPE = "a field in the request has the wrong type or size"


def _text(body: dict, key: str) -> Optional[str]:
    """An optional string field: absent, null or empty is None; anything but a string is refused."""
    value = body.get(key)
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _texts(body: dict, key: str) -> Optional[list]:
    """An optional list of strings."""
    value = body.get(key)
    if value is None or value == []:
        return None
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ValueError(f"{key} must be a list of strings")
    return value


def _object(body: dict, key: str) -> Optional[dict]:
    """An optional JSON object field."""
    value = body.get(key)
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be a JSON object")
    return value


def _body(body: Any) -> dict:
    if body is None:
        return {}
    if not isinstance(body, dict):
        raise ValueError("send a JSON object")
    return body


def _once(s: Store, body: dict, fn: Callable[[], "tuple[int, dict]"]) -> "tuple[int, dict]":
    """Run a write once per op_id (a retried click or a second window changes nothing)."""
    op_id = body.get("op_id")
    if op_id is None:
        return fn()
    if not isinstance(op_id, str) or not OP_RE.match(op_id):
        raise ValueError("op_id must be 1 to 80 letters, digits, '.', '_', ':' or '-'")
    with s.lock():
        seen = s.read_json(OPS_FILE, default=[]) or []
        if op_id in seen:
            return ok({"duplicate": True, "op_id": op_id})
        status, out = fn()
        if status < 400:
            s.write_json(OPS_FILE, (list(seen) + [op_id])[-OPS_KEEP:])
        return status, out


# --- reads ----------------------------------------------------------------------------------------

@_guard
def health() -> "tuple[int, dict]":
    zone = bridge.zone_name()
    return ok({"plugin": "unblockbruecke", "version": VERSION, "time_zone": {"zone": zone or None, "server_local": not zone}})


@_guard
def decks_get() -> "tuple[int, dict]":
    cat = decks_mod.catalog(store())
    st = _settings_factory()
    rows = [decks_mod.deck_summary(d) for d in sorted(cat["decks"].values(), key=lambda d: (d["source"] != "shipped", d["deck"]))]
    return ok({"decks": rows, "broken": cat["broken"],
               "autodraw": {"on": st["autodraw"], "decks": st["autodraw_decks"], "threshold": st["autodraw_threshold"]}})


@_guard
def deck_get(slug: str) -> "tuple[int, dict]":
    s = store()
    cat = decks_mod.catalog(s)
    deck = cat["decks"].get(slug)
    if deck is None:
        return fail(404, "unknown_deck", f"no deck named {slug}")
    stats = journal.stats(s)
    out = decks_mod.deck_summary(deck)
    for key in ("voice", "glossary"):
        if deck.get(key):
            out[key] = deck[key]
    out["cards"] = [{**c, "stats": {k: stats.get(f"{slug}/{c['id']}", {}).get(k, 0) for k in ("drawn", "helped", "not_now")}}
                    for c in deck["cards"]]
    out["editable"] = deck["source"] in ("own", "imported")
    out["edits_save_as"] = editor.target_for(cat, slug)[0]
    return ok({"deck": out})


@_guard
def today() -> "tuple[int, dict]":
    st = _settings_factory()
    day = service.card_of_day(store(), st)
    return ok({"enabled": st["card_of_day"], "date": bridge.today().isoformat(), "card": day["card"] if day else None})


@_guard
def journal_get(limit: Any = 50, by: str = "", session: str = "") -> "tuple[int, dict]":
    try:
        limit = max(1, min(200, int(limit or 50)))
    except (TypeError, ValueError, OverflowError):
        limit = 50
    s = store()
    rows = journal.rows(s)
    draws = journal.draws_from(rows, limit=limit, session=session or "", by=by or "")
    cat = decks_mod.catalog(s)
    for d in draws:
        deck = cat["decks"].get(d.get("deck", ""))
        card = decks_mod.find_card(deck, d.get("card", "")) if deck else None
        d["view"] = draw_mod.card_view(deck, card, d.get("face", "human")) if card else None
    stats = journal.stats_from(rows)
    totals = {k: sum(v[k] for v in stats.values()) for k in ("drawn", "helped", "not_now", "by_auto")}
    totals["draws"] = totals.pop("drawn")
    return ok({"draws": draws, "totals": totals, "learning": _settings_factory()["learning"]})


@_guard
def versions(slug: str) -> "tuple[int, dict]":
    return ok({"deck": slug, "versions": editor.versions(store(), slug)})


@_guard
def export(slug: str) -> "tuple[int, dict]":
    out = editor.export(store(), slug)
    out.pop("ok", None)
    return ok(out)


@_guard
def settings_get() -> "tuple[int, dict]":
    return ok({"settings": _settings_factory()})


# --- writes ---------------------------------------------------------------------------------------

@_guard
def draw(body: Any) -> "tuple[int, dict]":
    body = _body(body)
    s = store()
    context = body.get("context") or "any"
    if context not in ("any", "human", "stuck", "break"):
        raise ValueError("context must be any, human, stuck or break")
    deck, decks = _text(body, "deck"), _texts(body, "decks")

    def run():
        out = service.draw_card(s, _settings_factory(), deck=deck, decks=decks,
                                context=context, by="user", face=body.get("face"))
        return ok(out)
    return _once(s, body, run)


@_guard
def rate(body: Any) -> "tuple[int, dict]":
    body = _body(body)
    s = store()

    def run():
        try:
            row = journal.rate(s, str(body.get("draw_id") or ""), str(body.get("rating") or ""), by="user")
        except LookupError as exc:
            return fail(404, "unknown_draw", str(exc))
        return ok({"rated": {"draw_id": row["draw_id"], "rating": row["rating"]}})
    return _once(s, body, run)


@_guard
def reset(body: Any) -> "tuple[int, dict]":
    body = _body(body)
    s = store()
    return _once(s, body, lambda: ok({"reset_at": journal.reset_learning(s, "user")["at"]}))


@_guard
def preview(slug: str, body: Any) -> "tuple[int, dict]":
    body = _body(body)
    out = editor.preview(store(), slug, body.get("content"), _object(body, "changes"))
    if not out.get("ok"):
        return fail(422, "invalid_deck", out["message"], **decks_mod.problem_fields(out["problems"]), target=out.get("target"))
    out.pop("ok")
    return ok(out)


@_guard
def save(slug: str, body: Any) -> "tuple[int, dict]":
    body = _body(body)
    s = store()
    changes = _object(body, "changes")

    def run():
        out = editor.save(s, slug, str(body.get("confirm") or ""), "user", body.get("content"), changes,
                          replace=bool(body.get("replace")))
        out.pop("ok", None)
        return ok(out)
    return _once(s, body, run)


@_guard
def restore(slug: str, body: Any) -> "tuple[int, dict]":
    body = _body(body)
    s = store()

    def run():
        out = editor.restore(s, slug, body.get("version"), "user")
        out.pop("ok", None)
        return ok(out)
    return _once(s, body, run)


@_guard
def delete(slug: str, body: Any) -> "tuple[int, dict]":
    body = _body(body)
    s = store()

    def run():
        out = editor.delete(s, slug, "user")
        out.pop("ok", None)
        return ok(out)
    return _once(s, body, run)


@_guard
def import_deck(body: Any) -> "tuple[int, dict]":
    body = _body(body)
    text = body.get("yaml")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("send the deck file's text as yaml")
    s = store()

    def run():
        out = editor.import_text(s, text, "user", slug=body.get("slug") or None, replace=bool(body.get("replace")),
                                 origin=str(body.get("file_name") or "")[:80])
        out.pop("ok", None)
        return ok(out)
    return _once(s, body, run)


@_guard
def switch(body: Any) -> "tuple[int, dict]":
    body = _body(body)
    s = store()
    slug = body.get("deck")
    if not isinstance(slug, str):
        raise ValueError("deck must be a deck name (a string)")
    if "draw" not in body and "auto" not in body:
        raise ValueError("send draw and/or auto")
    for key in ("draw", "auto"):
        if key in body and not isinstance(body[key], bool):
            raise ValueError(f"{key} must be true or false")

    def run():
        if slug not in decks_mod.catalog(s)["decks"]:
            return fail(404, "unknown_deck", f"no deck named {slug}")
        decks_mod.set_switch(s, slug, draw=body.get("draw"), auto=body.get("auto"))
        return ok({"deck": slug, "switch": decks_mod.catalog(s)["decks"][slug]["switch"]})
    return _once(s, body, run)
