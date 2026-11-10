"""`unblockbruecke_decks`: the deck editor for the agent (F12, F13).

Edits always go preview first, then save with the preview's `confirm` value. Writes (save, restore,
delete, import, switch, export to a path) are refused in a run with nobody at the keyboard
(constraint 6). Every save keeps a version with author `agent`, so one call undoes it.
"""
from __future__ import annotations

from .. import decks as decks_mod, editor, service

ACTIONS = ("list", "get", "preview", "save", "versions", "restore", "delete", "switch", "import", "export")
WRITES = ("save", "restore", "delete", "switch", "import")

SCHEMA = {
    "name": "unblockbruecke_decks",
    "description": (
        "list, get, preview, save, versions, restore, delete, switch, import, export UnblockBrücke card decks. "
        "Edits change the user's own decks; editing a shipped deck saves an own copy '<deck>-own'. "
        "preview shows the diff of changes (or of a whole deck in content); save repeats the change with the "
        "preview's confirm value. "
        "Always preview and show the user the diff before save. "
        "versions lists saved versions; restore brings version n back; delete removes an own or imported deck. "
        "switch turns draw and auto on or off for one deck. "
        "import reads a YAML deck file at a full path the user names; export returns YAML, and with path writes "
        "a .yaml file. "
        "Change format and card rules: skill unblockbruecke:unblockbruecke."),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": list(ACTIONS)},
            "deck": {"type": "string", "description": "Deck name (slug), e.g. coding or my-music."},
            "changes": {"type": "object", "description": (
                "preview/save: {add: [{human, agent, tags}], edit: [{id, human?, agent?, tags?}], remove: [ids], "
                "meta: {name?, description?, mark?, glossary?}}.")},
            "content": {"type": "object", "description": "preview/save: a whole deck instead of changes."},
            "confirm": {"type": "string", "description": "save: the confirm value of the preview you showed."},
            "version": {"type": "integer", "description": "restore: a version number from versions."},
            "draw": {"type": "boolean", "description": "switch: drawing on or off."},
            "auto": {"type": "boolean", "description": "switch: auto-draw may use this deck."},
            "path": {"type": "string", "description": "import: the deck file; export: where to write (optional)."},
            "overwrite": {"type": "boolean", "description": "export: replace an existing deck file."},
            "replace": {"type": "boolean", "description": "import: replace your deck of the same name; save: replace a deck file that does not load."},
        },
        "required": ["action"],
    },
}


def handle(args: dict, rt) -> dict:
    action = args.get("action")
    if action not in ACTIONS:
        return {"ok": False, "error": "unknown_action", "message": f"action must be one of {', '.join(ACTIONS)}"}
    writes = action in WRITES or (action == "export" and args.get("path"))
    if writes:
        reason = rt.unattended()
        if reason:
            return {"ok": False, "error": "unattended",
                    "message": f"Refused: {action} changes the user's decks or files, and this run has no person at the "
                               f"keyboard ({reason}). Nothing was changed."}
    try:
        return globals()[f"_{action}"](args, rt)
    except editor.EditError as exc:
        return {"ok": False, "error": exc.code, "message": str(exc), **_jsonable(exc.extra)}
    except decks_mod.DeckError as exc:
        return {"ok": False, "error": exc.code, "message": str(exc), **decks_mod.problem_fields(exc.problems)}


def _jsonable(extra: dict) -> dict:
    return {k: v for k, v in extra.items() if k in ("problems", "problems_more", "preview")}


def _deck_arg(args: dict) -> str:
    slug = args.get("deck")
    if not isinstance(slug, str) or not slug:
        raise editor.EditError("name the deck (deck)")
    return slug


def _list(args: dict, rt) -> dict:
    cat = decks_mod.catalog(rt.store)
    return {"ok": True, "decks": [decks_mod.deck_summary(d) for d in sorted(cat["decks"].values(), key=lambda d: d["deck"])],
            **({"broken": cat["broken"]} if cat["broken"] else {})}


def _get(args: dict, rt) -> dict:
    cat = decks_mod.catalog(rt.store)
    deck = cat["decks"].get(_deck_arg(args))
    if deck is None:
        raise editor.EditError(f"no deck named {service.echo(args['deck'])}", "unknown_deck")
    out = {k: deck[k] for k in ("deck", "name", "by", "license", "version", "mark", "source", "switch") if k in deck}
    out.update({"description": deck.get("description"), "glossary": deck.get("glossary"), "cards": deck["cards"],
                "editable": deck["source"] in ("own", "imported"),
                "edits_save_as": editor.target_for(cat, deck["deck"])[0]})
    return {"ok": True, "deck": out}


def _preview(args: dict, rt) -> dict:
    out = editor.preview(rt.store, _deck_arg(args), args.get("content"), args.get("changes"))
    if out.get("ok"):
        out.pop("yaml", None)
        out["next"] = "Show the user this diff. If they agree, call save with the same change and this confirm value."
    return out


def _save(args: dict, rt) -> dict:
    return editor.save(rt.store, _deck_arg(args), str(args.get("confirm") or ""), rt.author,
                       args.get("content"), args.get("changes"), replace=bool(args.get("replace")))


def _versions(args: dict, rt) -> dict:
    return {"ok": True, "deck": args.get("deck"), "versions": editor.versions(rt.store, _deck_arg(args))}


def _restore(args: dict, rt) -> dict:
    return editor.restore(rt.store, _deck_arg(args), args.get("version"), rt.author)


def _delete(args: dict, rt) -> dict:
    return editor.delete(rt.store, _deck_arg(args), rt.author)


def _switch(args: dict, rt) -> dict:
    slug = _deck_arg(args)
    cat = decks_mod.catalog(rt.store)
    if slug not in cat["decks"]:
        raise editor.EditError(f"no deck named {service.echo(slug)}", "unknown_deck")
    if "draw" not in args and "auto" not in args:
        raise editor.EditError("switch takes draw and/or auto (true or false)")
    decks_mod.set_switch(rt.store, slug, draw=args.get("draw"), auto=args.get("auto"))
    return {"ok": True, "deck": slug, "switch": decks_mod.catalog(rt.store)["decks"][slug]["switch"]}


def _import(args: dict, rt) -> dict:
    path = args.get("path")
    if not path:
        raise editor.EditError("import needs the full path of a deck file the user named")
    return editor.import_file(rt.store, path, rt.author, slug=args.get("deck") or None, replace=bool(args.get("replace")))


def _export(args: dict, rt) -> dict:
    return editor.export(rt.store, _deck_arg(args), args.get("path") or None, bool(args.get("overwrite")))
