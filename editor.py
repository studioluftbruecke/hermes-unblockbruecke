"""Deck editor: preview with a diff, save with versions, restore, delete, import, export.

Shipped and community decks are never changed: an edit saves an own copy `<slug>-own` that replaces
the original for drawing. Every save keeps a version (`decks.versions/<slug>/<n>.yaml` plus an
`index.json` row with author, time and a one-line summary), the last `KEEP` per deck, so one save
can be undone from the page or by the agent.

A save must name the `confirm` value its preview returned: it is a hash of the file the preview
started from and the text it would write, so a save never lands on a deck that changed since the
preview (another window, the agent, a second route call), and the agent always shows the diff first.
A person's edit of an own deck (or a new one) saves at once, without a preview; the version
it writes is its Undo. The first own copy of a shipped deck, imported decks and the agent's edits keep
the preview. Tags are optional in the user's decks.
"""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Any, Optional

from . import bridge, decks as decks_mod, service
from .decks import DeckError, OWN_SUFFIX, USER_DIR
from .store import Store

VERSIONS = "decks.versions"
KEEP = 20
MAX_IMPORT_BYTES = decks_mod.MAX_FILE_BYTES
AUTHORS = ("user", "agent")
ADDED_TAG = "A tag added in this deck's editor."


class EditError(Exception):
    def __init__(self, message: str, code: str = "invalid", **extra: Any):
        super().__init__(message)
        self.code = code
        self.extra = extra


MESSAGE_CHARS = 160


def rules_message(lead: str, problems: list) -> str:
    """A short sentence for a broken deck: how many rules it breaks, the first one or two, and the same
    "and N more" count as the answer's `problems_more`. The `problems` list carries the rest."""
    fields = decks_mod.problem_fields(problems)
    listed, more = fields["problems"], fields.get("problems_more", 0)
    total = len(listed) + more
    tail = f" The list shows {len(listed)}, and {more} more." if more else ""
    head = f"{lead} {total} rule{'s' if total != 1 else ''}"
    lines = [f"{p['card'] + ': ' if p.get('card') else ''}{p['message']} ({p['rule']})" for p in listed]
    if not lines:
        return head + "."
    msg, hint = "", ""
    for k in range(min(len(lines), 3), 0, -1):
        hint = tail or (f" The list shows all {len(listed)}." if len(listed) > k else "")
        msg = f"{head}: {'; '.join(lines[:k])}.{hint}"
        if len(msg) <= MESSAGE_CHARS:
            return msg
    first = lines[0][:max(20, len(lines[0]) - (len(msg) - MESSAGE_CHARS) - 3)] + "..."
    return f"{head}: {first}.{hint}"


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def current_text(store: Store, slug: str) -> str:
    try:
        return store.path(USER_DIR, f"{slug}.yaml").read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def target_for(cat: dict, slug: str) -> tuple[str, Optional[dict]]:
    """(the user file an edit of `slug` writes, the deck the edit starts from or None for a new deck)."""
    if not isinstance(slug, str) or not decks_mod.SLUG_RE.fullmatch(slug):
        raise EditError("a file name is 2 to 40 characters of a-z, 0-9 and '-'")
    decks = cat["decks"]
    deck = decks.get(slug)
    if deck is not None and deck["source"] in ("shipped", "community"):
        own = f"{slug}{OWN_SUFFIX}"
        return own, decks.get(own) or deck
    if deck is None and slug in decks_mod.SHIPPED:
        raise EditError(f"'{slug}' is a shipped deck")
    if deck is None and slug.endswith(OWN_SUFFIX):
        # an own copy that does not exist yet starts from the deck it copies, so a save never makes an
        # unrelated deck that then takes the shipped one's place for drawing
        original = decks.get(slug[: -len(OWN_SUFFIX)])
        if original is not None and original["source"] in ("shipped", "community"):
            return slug, original
    return slug, deck


def _next_id(prefix: str, cards: list[dict]) -> str:
    used = {int(m.group(2)) for c in cards if (m := decks_mod.ID_RE.fullmatch(str(c.get("id", ""))))}
    n = 1
    while n in used:
        n += 1
    if n > 99:
        raise EditError("a deck holds ids up to 99")
    return f"{prefix}-{n:02d}"


def _prefix_for(slug: str, base: Optional[dict]) -> str:
    if base and base.get("prefix"):
        return base["prefix"]
    letters = re.sub(r"[^a-z]", "", slug)
    return (letters[:2] or "my").ljust(2, "x")


def build(slug: str, base: Optional[dict], deck: Optional[dict] = None, changes: Optional[dict] = None) -> dict:
    """The new deck document: a whole `deck`, or `changes` (add, edit, remove, meta) on the base."""
    if deck is not None:
        if not isinstance(deck, dict):
            raise EditError("deck must be an object")
        doc = {**_defaults(slug, base), **deck}
    else:
        if base is None and not changes:
            raise EditError("send the deck or the changes")
        doc = _defaults(slug, base)
        doc["cards"] = [dict(c) for c in (base or {}).get("cards") or []]
        doc["glossary"] = dict((base or {}).get("glossary") or {})
        ch = changes or {}
        if not isinstance(ch, dict):
            raise EditError("changes must be an object with add, edit, remove or meta")
        meta = ch.get("meta") or {}
        if not isinstance(meta, dict):
            raise EditError("meta must be an object, e.g. {name, description, glossary}")
        for key in ("name", "description", "voice", "mark", "area", "by", "license"):
            if key in meta:
                if not isinstance(meta[key], str):
                    raise EditError(f"meta {key} must be text")
                doc[key] = meta[key]
        if "glossary" in meta and meta["glossary"] is not None:
            glossary = meta["glossary"]
            if not isinstance(glossary, dict) or not all(isinstance(k, str) and isinstance(v, str)
                                                         for k, v in glossary.items()):
                raise EditError("meta glossary must map each tag to one line of text")
            doc["glossary"].update(glossary)
        remove_ids = _as_list(ch.get("remove"), "remove")
        if not all(isinstance(i, str) for i in remove_ids):
            raise EditError("remove is a list of card ids")
        remove = set(remove_ids)
        missing = remove - {c["id"] for c in doc["cards"]}
        if missing:
            raise EditError(f"no card {service.echo(sorted(missing))} in this deck")
        doc["cards"] = [c for c in doc["cards"] if c["id"] not in remove]
        for edit in _as_list(ch.get("edit"), "edit"):
            if not isinstance(edit, dict) or not isinstance(edit.get("id"), str):
                raise EditError("each edit is an object that names the card id")
            card = next((c for c in doc["cards"] if c["id"] == edit["id"]), None)
            if card is None:
                raise EditError(f"no card {service.echo(edit['id'])} in this deck")
            for key in ("human", "agent"):
                if key in edit:
                    card[key] = _text(edit[key], key)
            if "tags" in edit:
                card["tags"] = _tags(edit["tags"])
        prefix = _prefix_for(slug, base)
        for new in _as_list(ch.get("add"), "add"):
            if not isinstance(new, dict):
                raise EditError("each added card is an object with human, agent and tags")
            if new.get("id") is not None and not isinstance(new["id"], str):
                raise EditError("a card id is text like ab-01")
            card = {"id": new.get("id") or _next_id(prefix, doc["cards"]), "human": _text(new.get("human", ""), "human"),
                    "agent": _text(new.get("agent", ""), "agent"), "tags": _tags(new.get("tags"))}
            doc["cards"].append(card)
        # The page has no glossary field: a tag new to this deck gets a plain line the user can edit later.
        for card in doc["cards"]:
            for tag in card.get("tags") or []:
                if isinstance(tag, str) and tag not in doc["glossary"] and tag not in decks_mod.BUILTIN_TAGS:
                    doc["glossary"][tag] = "A card you wrote yourself." if tag == "own" else ADDED_TAG
    doc["deck"] = slug
    if base is not None and base.get("source") in ("own", "imported") and deck is None:
        doc["version"] = int(base.get("version", 1)) + 1
    return doc


def _as_list(value: Any, what: str) -> list:
    """A list argument: None is empty, one string is a one-item list, anything else but a list is refused."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return value
    raise EditError(f"{what} must be a list")


def _text(value: Any, face: str) -> str:
    if not isinstance(value, str):
        raise EditError(f"the {face} face must be text")
    return value


def _tags(value: Any) -> list:
    tags = _as_list(value, "tags")
    if not all(isinstance(t, str) for t in tags):
        raise EditError("tags is a list of tag names")
    return tags


def _defaults(slug: str, base: Optional[dict]) -> dict:
    if base is not None:
        out = {k: base[k] for k in ("schema", "name", "by", "license", "version", "faces", "mark", "description",
                                    "voice", "area") if k in base}
        if base.get("source") in ("shipped", "community"):
            out["name"] = f"{base['name']} (own)"[:40]
            out["version"] = 1
        return out
    return {"schema": 1, "name": slug.replace("-", " ").capitalize()[:40], "by": "Me", "license": "own", "version": 1,
            "faces": ["human", "agent"], "mark": "ring"}


def diff(old: Optional[dict], new: dict, ignore: tuple = ()) -> dict:
    before = {c["id"]: c for c in (old or {}).get("cards") or []}
    after = {c["id"]: c for c in new.get("cards") or []}
    changed = []
    for cid in after.keys() & before.keys():
        fields = [k for k in ("human", "agent", "tags") if after[cid].get(k) != before[cid].get(k)]
        if fields:
            changed.append({"id": cid, "fields": fields,
                            "before": {k: before[cid].get(k) for k in fields}, "after": {k: after[cid].get(k) for k in fields}})
    meta = [k for k in ("name", "description", "voice", "mark", "area", "by", "license", "glossary")
            if k not in ignore and (old or {}).get(k) != new.get(k)]
    out = {"added": [after[i] for i in after if i not in before], "removed": [before[i] for i in before if i not in after],
           "changed": sorted(changed, key=lambda c: c["id"]), "meta": meta if old else []}
    parts = []
    for key, word in (("added", "added"), ("changed", "changed"), ("removed", "removed")):
        if out[key]:
            parts.append(f"{len(out[key])} card{'s' if len(out[key]) != 1 else ''} {word}")
    if out["meta"]:
        parts.append("changed " + ", ".join(out["meta"]))
    out["summary"] = "; ".join(parts) or ("new deck" if not old else "no change")
    return out


def preview(store: Store, slug: str, deck: Optional[dict] = None, changes: Optional[dict] = None) -> dict:
    cat = decks_mod.catalog(store)
    target, base = target_for(cat, slug)
    doc = build(target, base, deck, changes)
    clean, problems = decks_mod.validate(doc, target, tags_required=False)
    if clean is None:
        return {"ok": False, "error": "invalid_deck", "target": target, **decks_mod.problem_fields(problems),
                "message": rules_message("The deck would break", problems)}
    text = decks_mod.dump_yaml(clean)
    base_text = current_text(store, target)
    first_copy = base is not None and base.get("source") in ("shipped", "community")
    change = diff(base, clean, ignore=("name",) if first_copy else ())
    if first_copy:
        change["summary"] = f"own copy of {slug}: {change['summary']}"
    return {"ok": True, "target": target, "copy_of": slug if target != slug else None, "diff": change,
            "summary": change["summary"], "yaml": text, "confirm": _hash(base_text + "\0" + text),
            "cards": len(clean["cards"])}


def saves_at_once(cat: dict, slug: str) -> bool:
    """Whether a person's edit of `slug` saves without a preview: it lands in an own deck (an own
    copy that already exists included) or makes a new one. False for the first own copy of a shipped or
    community deck and for imported decks."""
    try:
        target, base = target_for(cat, slug)
    except EditError:
        return False
    if base is None:
        return target not in cat["decks"]
    return base.get("source") == "own" and base.get("deck") == target


def save(store: Store, slug: str, confirm: str, author: str, deck: Optional[dict] = None,
         changes: Optional[dict] = None, replace: bool = False, at_once: bool = False) -> dict:
    """Save after a preview (`confirm`), or with `at_once` (a person's click) without one where
    `saves_at_once` allows it; a `confirm` that is sent is always checked."""
    if author not in AUTHORS:
        raise EditError("author must be user or agent")
    with store.lock():
        pv = preview(store, slug, deck, changes)
        if not pv["ok"]:
            raise EditError(pv["message"], "invalid_deck", **decks_mod.problem_fields(pv["problems"]))
        now = at_once and author == "user" and not confirm and saves_at_once(decks_mod.catalog(store), slug)
        if not now and confirm != pv["confirm"]:
            raise EditError("The deck changed since that preview, or the save differs from it. Preview again and "
                            "save with the new confirm value.", "stale_preview", preview=pv)
        if pv["diff"]["summary"] == "no change" and current_text(store, pv["target"]):
            return {"ok": True, "deck": pv["target"], "version": latest(store, pv["target"]), "summary": "no change",
                    "saved_at_once": bool(now)}
        if _unloadable(store, pv["target"]) and not replace:
            raise EditError(_UNLOADABLE.format(slug=pv["target"], what="save"), "exists")
        _keep_unrecorded(store, pv["target"], author, "kept before a save replaced it")
        before = _index(store, pv["target"])
        n = _write(store, pv["target"], pv["yaml"], author, pv["summary"])
    return {"ok": True, "deck": pv["target"], "version": n, "summary": pv["summary"], "diff": pv["diff"],
            "undo": _undo(before, n, pv["target"]), "saved_at_once": bool(now)}


def _undo(before: list[dict], n: int, slug: str) -> dict:
    """What undoes write `n`: the version before it, or deleting the deck when there was none."""
    if n > 1 and before and not before[-1].get("deleted"):
        return {"restore": n - 1}
    return {"delete": slug}


_UNLOADABLE = ("a deck file '{slug}' is already there, but it breaks the deck rules, so it does not load; {what} "
               "with replace to put this deck in its place (the old file is kept as a version)")


def _unloadable(store: Store, slug: str) -> bool:
    """True when the user folder holds a file of this name that the catalog does not load."""
    return bool(current_text(store, slug)) and slug not in decks_mod.catalog(store)["decks"]


def _keep_unrecorded(store: Store, slug: str, author: str, summary: str) -> None:
    """Keep the deck file as a version first when no version holds its text (written by hand, or after a
    delete), so the undo of the write that follows brings it back instead of losing it. Caller holds the lock."""
    text = current_text(store, slug)
    if not text:
        return
    idx = _index(store, slug)
    if idx and not idx[-1].get("deleted"):
        try:
            if store.path(VERSIONS, slug, f"{idx[-1]['n']}.yaml").read_text(encoding="utf-8") == text:
                return
        except FileNotFoundError:
            pass
    _write(store, slug, text, author, summary)


def _index(store: Store, slug: str) -> list[dict]:
    data = store.read_json(VERSIONS, slug, "index.json", default=[])
    return data if isinstance(data, list) else []


def latest(store: Store, slug: str) -> int:
    idx = _index(store, slug)
    return idx[-1]["n"] if idx else 0


def _switch_entry(store: Store, slug: str) -> Optional[dict]:
    entry = decks_mod.read_switches(store)["decks"].get(slug)
    return dict(entry) if isinstance(entry, dict) else None


def _write(store: Store, slug: str, text: str, author: str, summary: str, deleted: bool = False) -> int:
    """Write the deck (or remove it), record a version; caller holds the lock.

    Each index row keeps `switch_before`, the deck's switch entry (source, draw, auto) just before
    this write, so a restore can bring back the switch that belonged to the text it restores."""
    idx = _index(store, slug)
    n = (idx[-1]["n"] if idx else 0) + 1
    vpath = store.path(VERSIONS, slug, f"{n}.yaml")
    vpath.parent.mkdir(parents=True, exist_ok=True)
    vpath.write_text(text, encoding="utf-8")
    idx.append({"n": n, "at": bridge.iso(), "author": author, "summary": summary, "deleted": deleted,
                "switch_before": _switch_entry(store, slug) or {}})
    for old in idx[:-KEEP]:
        store.remove(VERSIONS, slug, f"{old['n']}.yaml")
    store.write_json((VERSIONS, slug, "index.json"), idx[-KEEP:])
    target = store.path(USER_DIR, f"{slug}.yaml")
    if deleted:
        store.remove(USER_DIR, f"{slug}.yaml")
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".yaml.tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(target)
    return n


def versions(store: Store, slug: str) -> list[dict]:
    if not isinstance(slug, str) or not decks_mod.SLUG_RE.fullmatch(slug):
        raise EditError("unknown deck", "unknown_deck")
    return list(reversed(_index(store, slug)))


def restore(store: Store, slug: str, n: Any, author: str) -> dict:
    if not isinstance(slug, str) or not decks_mod.SLUG_RE.fullmatch(slug):
        raise EditError("unknown deck", "unknown_deck")
    try:
        n = int(n)
    except (TypeError, ValueError, OverflowError):
        raise EditError("version must be a number from the versions list")
    with store.lock():
        idx = _index(store, slug)
        row = next((r for r in idx if r["n"] == n), None)
        if row is None:
            raise EditError(f"deck {slug} has no saved version {n}", "unknown_version")
        try:
            text = store.path(VERSIONS, slug, f"{n}.yaml").read_text(encoding="utf-8")
        except FileNotFoundError:
            raise EditError(f"version {n} of {slug} is no longer kept", "unknown_version")
        was_gone = not current_text(store, slug)
        _keep_unrecorded(store, slug, author, f"kept before version {n} was restored")
        idx = _index(store, slug)
        before = _load_or_none(current_text(store, slug), slug)
        # A kept file that never loaded (written by hand) comes back as it was, so its undo is exact.
        restored = _load_or_none(text, slug)
        if restored is None:
            change = {"summary": "file brought back as it was; it does not load until its rules are fixed"}
        else:
            change = diff(before, restored) if before else {"summary": "deck brought back"}
        current = _switch_entry(store, slug)
        snap = _switch_of_version(idx, n)
        new_n = _write(store, slug, text, author, f"restored version {n}: {change['summary']}")
        # The switch comes back with the text when the deck was gone, its source differs (an import
        # replaced an own deck, or the reverse), or an import ended that version (an import turns auto
        # off); a plain restore keeps today's switches.
        if snap is not None and (current is None or snap.get("source", "own") != current.get("source", "own")
                                 or (_ended_by_import(idx, n) and _same_switch(snap) != _same_switch(current))):
            decks_mod.forget_switch(store, slug)
            if snap:
                decks_mod.set_switch(store, slug, draw=snap.get("draw"), auto=snap.get("auto"),
                                     source=snap.get("source"))
    # Undoing a restore that brought a deleted deck back removes it again.
    return {"ok": True, "deck": slug, "version": new_n, "restored": n, "summary": change["summary"],
            "undo": {"delete": slug} if was_gone else {"restore": new_n - 1}}


def _ended_by_import(idx: list[dict], n: int) -> bool:
    pos = next(i for i, r in enumerate(idx) if r["n"] == n)
    return pos + 1 < len(idx) and str(idx[pos + 1].get("summary", "")).startswith("imported")


def _same_switch(entry: Optional[dict]) -> tuple:
    entry = entry or {}
    return entry.get("source", "own"), entry.get("draw"), entry.get("auto")


def _switch_of_version(idx: list[dict], n: int) -> Optional[dict]:
    """The switch entry that belonged to version `n`: kept on the row that ended it (the next row, or
    the deletion row itself). None when the rows predate this record; an import in the history then
    still counts as imported, so restored imported text never comes back on for auto-draw."""
    pos = next(i for i, r in enumerate(idx) if r["n"] == n)
    holder = idx[pos] if idx[pos].get("deleted") else (idx[pos + 1] if pos + 1 < len(idx) else None)
    if holder is None:
        return None
    snap = holder.get("switch_before")
    if isinstance(snap, dict):
        return snap
    if any(str(r.get("summary", "")).startswith("imported") for r in idx[:pos + 1]):
        return {"source": "imported", "auto": False}
    return None


def _load_or_none(text: str, slug: str) -> Optional[dict]:
    if not text:
        return None
    try:
        return decks_mod.load_text(text, slug, tags_required=False)
    except DeckError:
        return None


def delete(store: Store, slug: str, author: str) -> dict:
    if not isinstance(slug, str) or not decks_mod.SLUG_RE.fullmatch(slug):
        raise EditError("unknown deck", "unknown_deck")
    with store.lock():
        deck = decks_mod.catalog(store)["decks"].get(slug)
        if deck is None:
            raise EditError(f"no deck named {slug}", "unknown_deck")
        if deck["source"] not in ("own", "imported"):
            raise EditError("only your own and imported decks can be deleted; switch shipped decks off instead")
        n = _write(store, slug, current_text(store, slug), author, "deleted", deleted=True)
        decks_mod.forget_switch(store, slug)  # the deletion row keeps it for the undo
    return {"ok": True, "deck": slug, "version": n, "summary": "deleted", "undo": {"restore": n}}


def import_file(store: Store, path: str, author: str, slug: Optional[str] = None, replace: bool = False) -> dict:
    p = Path(str(path)).expanduser()
    if not p.is_absolute():
        raise EditError("give the full path of the deck file")
    try:
        if p.stat().st_size > MAX_IMPORT_BYTES:
            raise EditError(f"the file is larger than {MAX_IMPORT_BYTES // 1024} KB")
        text = p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise EditError(f"cannot read {p}: {exc}")
    return import_text(store, text, author, slug=slug, replace=replace, origin=p.name)


def import_text(store: Store, text: str, author: str, slug: Optional[str] = None, replace: bool = False,
                origin: str = "") -> dict:
    doc = decks_mod.parse_yaml(text)
    if not isinstance(doc, dict):
        raise EditError("the file is not a deck")
    if slug is not None and not isinstance(slug, str):
        raise EditError("the file name must be text")
    named = doc.get("deck")
    slug = slug or (named if isinstance(named, str) else "")
    doc = {**doc, "deck": slug}
    deck, problems = decks_mod.validate(doc, slug, tags_required=False, file=True)
    if deck is None:
        raise EditError(rules_message("The deck breaks", problems), "invalid_deck", **decks_mod.problem_fields(problems))
    if slug in decks_mod.SHIPPED:
        raise EditError(f"'{slug}' is the name of a shipped deck; import it under another file name", "exists")
    dropped = deck.pop("unknown_keys", None)
    with store.lock():
        loaded = slug in decks_mod.catalog(store)["decks"]
        existed = loaded or bool(current_text(store, slug))
        if existed and not replace:
            if not loaded:
                raise EditError(_UNLOADABLE.format(slug=slug, what="import"), "exists")
            raise EditError(f"you already have a deck '{slug}'; import under another name or replace it", "exists")
        _keep_unrecorded(store, slug, author, "kept before an import replaced it")
        before = _index(store, slug) if existed else []
        n = _write(store, slug, decks_mod.dump_yaml(deck), author, f"imported{' from ' + origin if origin else ''}")
        decks_mod.set_switch(store, slug, source="imported", auto=False)
    return {"ok": True, "deck": slug, "version": n, "cards": len(deck["cards"]), "source": "imported",
            "replaced": existed, "undo": _undo(before, n, slug),
            "note": "Hermes does not draw from an imported deck until you switch that on; you can draw from it now."
                    + (f" Not kept: {', '.join(dropped)[:200]} (keys this version does not know)." if dropped else "")}


def export(store: Store, slug: str, path: Optional[str] = None, overwrite: bool = False) -> dict:
    cat = decks_mod.catalog(store)
    deck = cat["decks"].get(slug)
    if deck is None:
        raise EditError(f"no deck named {service.echo(slug)}", "unknown_deck")
    text = decks_mod.dump_yaml(deck)
    out: dict = {"ok": True, "deck": slug, "file_name": f"{slug}.yaml", "yaml": text}
    if path:
        p = Path(str(path)).expanduser()
        if not p.is_absolute():
            raise EditError("give the full path to write to")
        if p.is_dir():
            p = p / f"{slug}.yaml"
        if p.suffix.lower() not in EXPORT_SUFFIXES:
            raise EditError("export writes only a .yaml or .yml file; name a folder or a file ending in .yaml")
        if not p.parent.is_dir():
            raise EditError(f"the folder {p.parent} does not exist")
        if _inside_plugin(store, p):
            raise EditError("export does not write into Unblockbrücke's own folders (its data or the plugin); "
                            "choose a folder of your own")
        if p.exists() or p.is_symlink():
            if not overwrite:
                raise EditError(f"{p} exists; pass overwrite to replace it", "exists")
            if not _is_deck_file(p):
                raise EditError(f"{p} is not a deck file, so export does not replace it; choose another name")
        _write_no_follow(p, text)
        out["written"] = str(p)
    return out


EXPORT_SUFFIXES = (".yaml", ".yml")


def _inside_plugin(store: Store, p: Path) -> bool:
    """True when the target (links followed) lies in the plugin's data folder or the plugin folder."""
    target = p.parent.resolve() / p.name
    real = p.resolve()
    for root in (store.root, decks_mod.PLUGIN_ROOT):
        root = Path(root).resolve()
        if any(t == root or root in t.parents for t in (target, real)):
            return True
    return False


def _write_no_follow(p: Path, text: str) -> None:
    """Write the file without following a link put in its place after the checks."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(p, flags, 0o644)
    except OSError as exc:
        raise EditError(f"cannot write {p}: {exc.strerror or exc}")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)


def _is_deck_file(p: Path) -> bool:
    """True for a plain file (not a link) that parses as a deck: a mapping with a deck name and cards."""
    try:
        if p.is_symlink() or not p.is_file() or p.stat().st_size > MAX_IMPORT_BYTES:
            return False
        doc = decks_mod.parse_yaml(p.read_text(encoding="utf-8"))
    except Exception:
        return False
    return isinstance(doc, dict) and isinstance(doc.get("deck"), str) and isinstance(doc.get("cards"), list)
