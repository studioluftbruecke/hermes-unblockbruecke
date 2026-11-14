"""The routes' logic, without FastAPI, so tests call it directly: each function returns (status, body).

`dashboard/plugin_api.py` only adapts these to FastAPI. Every body carries `schema`; errors are
`{ok: false, schema, error, message, problems?}`. These are the user's own clicks
(author `user`), so no unattended check runs here; for every profile except the dashboard's own,
routes run in the profile's plugin host child. Writes take an optional `op_id`: a repeat answers
`duplicate: true` and changes nothing.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Optional

from . import bridge, decks as decks_mod, draw as draw_mod, editor, journal, service, settings as settings_mod
from .store import Store, StoreError, default_root, hermes_home

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

# Hermes' public CLI, run by the Python that runs this process (so the same Hermes install), as an
# argument list without a shell.
HERMES_CLI = [sys.executable, "-m", "hermes_cli.main"]
# The child gets only what the CLI needs, never the secrets this process holds.
CHILD_ENV = ("PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE", "TZ", "PYTHONPATH", "VIRTUAL_ENV", "TMPDIR",
             "HERMES_DISABLE_LAZY_INSTALLS")
# What Hermes reads to find the profile's config and to decide whether it may write it (a managed install,
# an administrator's pinned keys, a remote config backend, the file modes and owner a container wants), so
# Hermes' own refusals hold in the child. None of them holds a secret.
HERMES_WRITE_ENV = ("HERMES_MANAGED", "HERMES_MANAGED_DIR", "HERMES_CONFIG_BACKEND", "HERMES_DEV", "HERMES_CONTAINER",
                    "HERMES_SKIP_CHMOD", "HERMES_HOME_MODE", "HERMES_UID", "HERMES_GID")
SAVE_TIMEOUT_S = 60
MANAGED_REFUSAL = "Plugin settings cannot be changed in a managed install."
ADMINISTRATOR_REFUSAL = "This setting is managed by your administrator and cannot be changed here."
LOCKED_REFUSAL = "This setting is locked by Remote Config and cannot be changed here."
SAVE_FAILED = "Hermes could not save the setting."
NOT_SAVED = "Hermes did not save the setting; the profile's config holds another value"


def _known_refusal(output: str) -> Optional[str]:
    """Recognize Hermes' refusal contracts without exposing its startup output, paths or other details."""
    text = output.lower()
    if "managed by your administrator" in text or "administrator-managed" in text:
        return ADMINISTRATOR_REFUSAL
    if any("is locked by the " in line and " level" in line for line in text.splitlines()):
        return LOCKED_REFUSAL
    if ("plugin settings cannot be changed in a managed install" in text
            or "this hermes installation is managed" in text or "this install is managed" in text):
        return MANAGED_REFUSAL
    return None


def _save_setting(key: str, value: Any) -> None:
    """`hermes config set plugins.entries.unblockbruecke.settings.<key> <value>` for the profile whose home
    is bound now: Hermes writes its own config.yaml, under its own lock. Raises PermissionError with a stable
    plugin-owned reason when Hermes refuses or the requested value does not land."""
    text = ("true" if value else "false") if isinstance(value, bool) else str(value)
    env = {name: os.environ[name] for name in (*CHILD_ENV, *HERMES_WRITE_ENV) if name in os.environ}
    env["HERMES_HOME"] = str(hermes_home())
    run = subprocess.run([*HERMES_CLI, "config", "set", f"plugins.entries.unblockbruecke.settings.{key}", text],
                         env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=SAVE_TIMEOUT_S)
    refusal = _known_refusal(run.stdout + "\n" + run.stderr)
    if run.returncode != 0:
        raise PermissionError(refusal or SAVE_FAILED)
    # A managed install makes `config set` print its refusal and exit 0, so the value Hermes now holds decides.
    got = settings_mod.saved_value(key)
    if type(got) is not type(value) or got != value:
        raise PermissionError(refusal or NOT_SAVED)


# Tests point these at a temp folder and fixed settings; in Hermes they follow the bound home per call.
_store_factory: Callable[[], Store] = lambda: Store(lambda: default_root())  # noqa: E731
_settings_factory: Callable[[], dict] = settings_mod.load_route_settings
_setting_saver: Callable[[str, Any], None] = _save_setting
_unattended: Callable[[], Optional[str]] = bridge.route_unattended


def configure(store_factory: Optional[Callable[[], Store]] = None,
              settings_factory: Optional[Callable[[], dict]] = None,
              setting_saver: Optional[Callable[[str, Any], None]] = None,
              unattended: Optional[Callable[[], Optional[str]]] = None) -> None:
    global _store_factory, _settings_factory, _setting_saver, _unattended
    _store_factory = store_factory or (lambda: Store(lambda: default_root()))
    _settings_factory = settings_factory or settings_mod.load_route_settings
    _setting_saver = setting_saver or _save_setting
    _unattended = unattended or bridge.route_unattended


def _seeded(s: Store, st: dict) -> None:
    service.ensure_seed(s, st)


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
    if not isinstance(op_id, str) or not OP_RE.fullmatch(op_id):
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
    s, st = store(), _settings_factory()
    _seeded(s, st)
    cat = decks_mod.catalog(s)
    rows = [decks_mod.deck_summary(d) for d in sorted(cat["decks"].values(), key=lambda d: (d["source"] != "shipped", d["deck"]))]
    return ok({"decks": rows, "broken": cat["broken"],
               "autodraw": {"on": st["autodraw"], "decks": [d["deck"] for d in decks_mod.hermes_decks(cat)],
                            "threshold": st["autodraw_threshold"]}})


@_guard
def deck_get(slug: str) -> "tuple[int, dict]":
    s = store()
    _seeded(s, _settings_factory())
    cat = decks_mod.catalog(s)
    deck = cat["decks"].get(slug)
    if deck is None:
        return fail(404, "unknown_deck", f"no deck named {service.echo(slug)}")
    stats = journal.stats(s)
    out = decks_mod.deck_summary(deck)
    for key in ("voice", "glossary"):
        if deck.get(key):
            out[key] = deck[key]
    out["cards"] = [{**c, "stats": {k: stats.get(f"{slug}/{c['id']}", {}).get(k, 0) for k in ("drawn", "helped", "not_now")}}
                    for c in deck["cards"]]
    out["editable"] = deck["source"] in ("own", "imported")
    out["edits_save_as"] = editor.target_for(cat, slug)[0]
    out["saves_at_once"] = editor.saves_at_once(cat, slug)
    return ok({"deck": out})


@_guard
def today() -> "tuple[int, dict]":
    st = _settings_factory()
    day = service.card_of_day(store(), st)
    return ok({"enabled": st["card_of_day"], "date": bridge.today().isoformat(), "card": day["card"] if day else None})


@_guard
def journal_get(limit: Any = 50, by: str = "", session: str = "") -> "tuple[int, dict]":
    if by not in ("", "user", "agent", "auto", "hermes"):
        raise ValueError("by must be user, agent, auto or hermes")
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


SUMMARY_KEYS = ("deck", "name", "mark", "source", "switch", "cards", "auto_cards", "shadowed_by", "copy_of")


def _settings_body() -> dict:
    """GET /settings: the settings, the keys the page may write, each deck's two
    switches, the decks Hermes draws from now and the example card under the switch."""
    s, st = store(), _settings_factory()
    _seeded(s, st)
    cat = decks_mod.catalog(s)
    rows = []
    for d in sorted(cat["decks"].values(), key=lambda d: (d["source"] != "shipped", d["deck"])):
        summary = decks_mod.deck_summary(d)
        rows.append({k: summary[k] for k in SUMMARY_KEYS if k in summary})
    return {"settings": settings_mod.public(st), "settable": list(settings_mod.SETTABLE),
            "ranges": {k: list(v) for k, v in settings_mod.RANGES.items()},
            "decks": rows,
            "hermes": {"decks": [d["deck"] for d in decks_mod.hermes_decks(cat)],
                       "example": service.hermes_example(s, cat)}}


@_guard
def settings_get() -> "tuple[int, dict]":
    return ok(_settings_body())


@_guard
def setting_set(body: Any) -> "tuple[int, dict]":
    """POST /setting: one of five keys, a person's click only. Saved through Hermes' CLI."""
    body = _body(body)
    key = body.get("key")
    if key not in settings_mod.SETTABLE:
        return fail(400, "unknown_setting", "This page saves only " + ", ".join(settings_mod.SETTABLE[:-1]) + " and "
                    + settings_mod.SETTABLE[-1] + ".", settable=list(settings_mod.SETTABLE))
    value = settings_mod.check_value(key, body.get("value"))  # ValueError: 400 invalid
    reason = _unattended()
    if reason:
        return fail(403, "unattended", f"Refused: a setting is a person's choice, and this run has no person at the "
                                       f"keyboard ({reason}). Nothing was changed.")
    s = store()

    def run():
        try:
            _setting_saver(key, value)
        except PermissionError as exc:
            return fail(403, "not_allowed", str(exc) or "Hermes does not allow changing this setting here.")
        except Exception as exc:  # noqa: BLE001 - the page needs a code, the log keeps the rest
            log.info("unblockbruecke: saving %s failed: %r", key, exc)
            return fail(500, "save_failed", f"The setting was not saved ({type(exc).__name__}).")
        return ok({**_settings_body(), "saved": {"key": key, "value": value}})
    return _once(s, body, run)


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
                          replace=bool(body.get("replace")), at_once=True)
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
        _seeded(s, _settings_factory())
        if slug not in decks_mod.catalog(s)["decks"]:
            return fail(404, "unknown_deck", f"no deck named {service.echo(slug)}")
        decks_mod.set_switch(s, slug, draw=body.get("draw"), auto=body.get("auto"))
        return ok({"deck": slug, "switch": decks_mod.catalog(s)["decks"][slug]["switch"]})
    return _once(s, body, run)
