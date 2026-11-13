"""Decks as data (F1): the file shape, the plain-text rules, loading and merging.

A deck is a YAML file read with `ruamel.yaml`'s safe loader (U9; PyYAML is not in Hermes' venv).
Three sources, merged in this order:

1. shipped: `data/decks/*.yaml` in the plugin (read-only), loaded once at import;
2. community: `data/decks/community/*.yaml` in the plugin (merged pull requests, read-only);
3. user: `decks/*.yaml` in the data folder: the user's own decks, imported decks, and own copies of
   shipped decks. An own copy is saved as `<slug>-own` and replaces `<slug>` for drawing.

The loader refuses a card that breaks a rule and names the rule (contract §2, PLAN constraint 5):
auto-draw puts a deck's text into the model's context, so card text is plain text only.
The Desktop never parses YAML: routes answer JSON.
"""
from __future__ import annotations

import io
import os
import re
import threading
from pathlib import Path
from typing import Any, Optional

from .store import Store, StoreError

PLUGIN_ROOT = Path(__file__).resolve().parent
SHIPPED_DIR = PLUGIN_ROOT / "data" / "decks"
COMMUNITY_DIR = SHIPPED_DIR / "community"
USER_DIR = "decks"
SWITCHES_FILE = "decks.json"

SCHEMA = 1
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,39}$")
ID_RE = re.compile(r"^([a-z]{2,4})-(\d{2})$")
TAG_RE = re.compile(r"^[a-z][a-z0-9-]{1,20}$")
LICENSES = ("CC-BY-4.0", "CC0-1.0", "own")
# 0.2: a glyph per shipped deck (the sketch pick); own decks may keep 0.1's six shapes.
MARKS = ("person", "code", "pencil", "shapes", "sphere", "robot",
         "square", "circle", "triangle", "diamond", "half", "ring")
HUMAN_MAX, AGENT_MAX = 90, 220
MAX_CARDS = 200
MAX_FILE_BYTES = 256 * 1024
MAX_PROBLEMS = 50
MAX_DEPTH = 20
OWN_SUFFIX = "-own"

BUILTIN_TAGS = {
    "human": "Asks a person something, so Hermes never draws it on its own when nobody is at the keyboard.",
    "auto": "Written for Hermes when its tool calls keep failing; Hermes draws only these when stuck.",
}

# Plain-text rules (contract §2). Each: (rule id, compiled pattern, what the user reads).
TEXT_RULES: list[tuple[str, re.Pattern, str]] = [
    ("html", re.compile(r"<\s*[A-Za-z/!]"), "no HTML tags"),
    ("markdown_link", re.compile(r"\[[^\[\]]*\]\([^)]*\)"), "no Markdown links"),
    ("code", re.compile(r"`"), "no backticks or code fences"),
    ("url", re.compile(r"(?i)\b(?:https?://|ftp://|www\.)|\b[a-z0-9-]+\.(?:com|org|net|io|de|dev|app|ai|co|uk|info|xyz|me)\b"),
     "no web addresses"),
    ("shell", re.compile(r"\$\(|\|\s*(?:sudo\s+)?(?:ba|z|da|k)?sh\b|\brm\s+-|\bsudo\b|\bcurl\b|\bwget\b|\bchmod\b|\bgit\s+push\b"),
     "no shell commands"),
]

DECK_KEYS = ("schema", "deck", "name", "by", "license", "version", "faces", "mark", "cards")


class Problems(list):
    """At most `MAX_PROBLEMS` problem lines; `more` counts the ones left out (answers say `problems_more`)."""

    more = 0


def capped(probs: list) -> Problems:
    out = Problems(probs[:MAX_PROBLEMS])
    out.more = problems_more(probs) + max(0, len(probs) - MAX_PROBLEMS)
    return out


def problems_more(probs: Any) -> int:
    """How many problem lines a capped list left out (0 for a plain list)."""
    return int(getattr(probs, "more", 0) or 0)


def problem_fields(probs: Any) -> dict:
    """The answer fields for a problem list: `problems` (at most `MAX_PROBLEMS`) and, when lines were left
    out, `problems_more`."""
    out = probs if isinstance(probs, Problems) else capped(list(probs or []))
    return {"problems": out, **({"problems_more": out.more} if out.more else {})}


class DeckError(Exception):
    """A deck that cannot be used, with the rules it broke (at most `MAX_PROBLEMS`, `problems_more` the rest)."""

    def __init__(self, message: str, problems: Optional[list] = None, code: str = "invalid_deck"):
        super().__init__(message)
        self.problems = capped(list(problems or [])) if not isinstance(problems, Problems) else problems
        self.problems_more = problems_more(self.problems)
        self.code = code


def problem(rule: str, message: str, card: Optional[str] = None) -> dict:
    return {"rule": rule, "card": card, "message": message}


def text_problems(text: Any, face: str, limit: int, card: Optional[str]) -> list[dict]:
    out: list[dict] = []
    if not isinstance(text, str) or not text.strip():
        return [problem(f"length_{face}", f"the {face} face is missing", card)]
    if len(text) > limit:  # the length answers first: no pattern runs on text the rules refuse anyway
        return [problem(f"length_{face}", f"the {face} face has {len(text)} characters (at most {limit})", card)]
    if "\n" in text or "\r" in text:
        out.append(problem("one_line", f"the {face} face has a line break", card))
    for rule, pattern, words in TEXT_RULES:
        if pattern.search(text):
            out.append(problem(rule, f"the {face} face breaks the rule: {words}", card))
    return out


def meta_problems(what: str, text: str) -> list[dict]:
    """The plain-text rules for deck metadata (name, description, glossary lines)."""
    return [problem(rule, f"{what} breaks the rule: {words}")
            for rule, pattern, words in TEXT_RULES if pattern.search(text)]


def _yaml():
    from ruamel.yaml import YAML

    return YAML(typ="safe", pure=True)


_FLOW_TOKEN = re.compile(r"[\[\]{}\"'#]")
# Quoted scalars the pre-scan skips end on their own line: a quote it misread (a plain line that goes
# on below) could otherwise hide the lines after it, where the parser sees real nesting.
_DOUBLE_QUOTED = re.compile(r'"(?:[^"\\\n]|\\.)*"')
_SINGLE_QUOTED = re.compile(r"'(?:[^'\n]|'')*'")
_SCALAR_START = "\n\r[{,"  # a value starts right after these
_LEAD = re.compile(r"[ \t]*(?:[-?][ \t]+)*")  # a line's indentation and block indicators ('- ', '? ')
_LEAD_MAX = 128


def _value_starts(text: str, i: int, j: int, depth: int, line_start: int) -> bool:
    """Whether a YAML value can start at `i`; `j` is the last non-blank position before it.

    YAML's rule: ':' opens a value only before whitespace ('a:[' is plain text), except after a
    JSON-like key inside a flow collection ({"a":"b"}); '-' and '?' only at the start of a line's
    content in block context ('Step - "a' is plain text)."""
    if j < 0:
        return True
    prev = text[j]
    if prev in _SCALAR_START:
        return True
    if prev == ":":
        return j < i - 1 or (bool(depth) and j > 0 and text[j - 1] in "\"']}")
    if prev in "-?" and j < i - 1 and not depth:
        return j - line_start <= _LEAD_MAX and _LEAD.fullmatch(text, line_start, j) is not None
    return False


def flow_depth(text: str, stop: int = MAX_DEPTH) -> int:
    """How deep `[` and `{` nest (stops counting past `stop`). A pre-scan, cheaper than the parser: an
    opener counts where a YAML value can start, quoted scalars and comments are skipped, and inside a
    flow collection every bracket counts (plain text there may not hold one).

    A quote opens a quoted scalar only where a value starts and when it closes on the same line; a
    quote inside plain text (`it's`, `a"b`) or one that does not close there is passed over and the
    scan goes on, so no quote can switch it off."""
    depth = deepest = pos = line_start = 0
    while True:
        m = _FLOW_TOKEN.search(text, pos)
        if m is None:
            return deepest
        i, c = m.start(), m.group()
        nl = text.rfind("\n", pos, i)  # only the stretch since the last token: linear overall
        if nl >= 0:
            line_start = nl + 1
        j = i - 1
        while j >= 0 and text[j] in " \t":
            j -= 1
        prev = text[j] if j >= 0 else "\n"
        at_start = _value_starts(text, i, j, depth, line_start)
        pos = i + 1
        if c == "#":
            if j < i - 1 or prev in "\n\r":  # a comment runs to the end of the line
                nl = text.find("\n", i)
                if nl < 0:
                    return deepest
                pos = nl
        elif c in "\"'":
            if at_start:
                q = (_DOUBLE_QUOTED if c == '"' else _SINGLE_QUOTED).match(text, i)
                if q is not None:  # else an open quote: scan on, the parser names the line
                    pos = q.end()
        elif c in "[{":
            if at_start or depth:
                depth += 1
                deepest = max(deepest, depth)
                if deepest > stop:
                    return deepest
        elif depth:
            depth -= 1


def parse_yaml(text: str) -> Any:
    if len(text.encode("utf-8")) > MAX_FILE_BYTES:
        raise DeckError(f"the file is larger than {MAX_FILE_BYTES // 1024} KB", code="too_large")
    if flow_depth(text) > MAX_DEPTH:  # the parser's time grows much faster than the nesting
        raise DeckError(f"not valid YAML: lists or mappings nest deeper than {MAX_DEPTH} levels", code="bad_yaml")
    try:
        return _yaml().load(text)
    except Exception as exc:  # ruamel raises many types; the user needs the line, not the class
        raise DeckError(f"not valid YAML: {str(exc).splitlines()[0] if str(exc) else type(exc).__name__}",
                        code="bad_yaml") from exc


def dump_yaml(deck: dict) -> str:
    """A deck as YAML in the file shape (key order of the contract, no source fields)."""
    from ruamel.yaml import YAML

    y = YAML()
    y.default_flow_style = False
    y.width = 4096
    y.allow_unicode = True
    doc = file_shape(deck)
    buf = io.StringIO()
    y.dump(doc, buf)
    return buf.getvalue()


def file_shape(deck: dict) -> dict:
    keys = ("schema", "deck", "name", "by", "license", "version", "faces", "mark", "description", "voice",
            "area", "glossary", "cards")
    out = {k: deck[k] for k in keys if k in deck and deck[k] not in (None, "", {})}
    out["schema"] = SCHEMA
    if out.get("glossary"):
        # Sorted, so the same deck always writes the same file (the editor's confirm hash relies on it).
        out["glossary"] = {k: out["glossary"][k] for k in sorted(out["glossary"])}
    out["cards"] = [{"id": c["id"], "human": c["human"], "agent": c["agent"], "tags": list(c.get("tags") or [])}
                    for c in deck.get("cards") or []]
    return out


def validate(doc: Any, slug: Optional[str] = None, tags_required: bool = True) -> tuple[Optional[dict], list[dict]]:
    """(normalised deck or None, problems). `slug` is the file name the deck must match, if any.
    `tags_required`: shipped and community deck files need 1 to 4 tags per card; the user's own and
    imported decks may have none (0.2, D21).

    Never raises: a field of the wrong type is a problem line like any other rule."""
    try:
        deck, probs = _validate(doc, slug, tags_required)
        return deck, capped(probs)
    except Exception as exc:  # a shape no rule foresaw is still a refusal, never a crash of the catalog
        return None, [problem("shape", f"the deck has a shape the loader cannot read ({type(exc).__name__})")]


def _face(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _validate(doc: Any, slug: Optional[str], tags_required: bool = True) -> tuple[Optional[dict], list[dict]]:
    probs: list[dict] = []
    if not isinstance(doc, dict):
        return None, [problem("shape", "a deck file is a mapping with deck, name, cards, ...")]
    for key in DECK_KEYS:
        if key not in doc:
            probs.append(problem("missing", f"the deck has no '{key}'"))
    if probs:
        return None, probs
    if doc.get("schema") != SCHEMA:
        probs.append(problem("schema", f"schema must be {SCHEMA}"))
    deck_slug = doc.get("deck")
    if not isinstance(deck_slug, str) or not SLUG_RE.match(deck_slug):
        probs.append(problem("slug", "deck must be 2 to 40 characters of a-z, 0-9 and '-'"))
    elif slug is not None and deck_slug != slug:
        probs.append(problem("slug", f"deck '{deck_slug}' must equal the file name '{slug}'"))
    for key, limit, required in (("name", 40, True), ("by", 80, True), ("description", 80, False),
                                 ("voice", 120, False), ("area", 40, False)):
        value = doc.get(key)
        if value is None and not required:
            continue
        if not isinstance(value, str) or (required and not value.strip()) or len(value) > limit or "\n" in value:
            probs.append(problem(key, f"{key} must be one line of {'1' if required else '0'} to {limit} characters"))
        else:
            probs += meta_problems(key, value)
    if doc.get("license") not in LICENSES:
        probs.append(problem("license", f"license must be one of {', '.join(LICENSES)}"))
    version = doc.get("version")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        probs.append(problem("version", "version must be a whole number from 1"))
    if doc.get("faces") != ["human", "agent"]:
        probs.append(problem("faces", "faces must be [human, agent]"))
    if doc.get("mark") not in MARKS:
        probs.append(problem("mark", f"mark must be one of {', '.join(MARKS)}"))
    glossary = doc.get("glossary") or {}
    if not isinstance(glossary, dict):
        probs.append(problem("glossary", "glossary must map each tag to a plain sentence"))
        glossary = {}
    clean_glossary: dict[str, str] = {}
    for tag, words in glossary.items():
        if (not isinstance(tag, str) or not TAG_RE.match(tag) or not isinstance(words, str) or not words.strip()
                or len(words) > 120 or "\n" in words):
            probs.append(problem("glossary", f"glossary entry '{tag}' needs a tag name and one line of at most 120 characters"))
            continue
        probs += meta_problems(f"glossary '{tag}'", words)
        clean_glossary[tag] = words.strip()
    cards = doc.get("cards")
    if not isinstance(cards, list) or not cards:
        probs.append(problem("cards", "a deck needs at least one card"))
        cards = []
    if len(cards) > MAX_CARDS:
        probs.append(problem("cards", f"a deck holds at most {MAX_CARDS} cards"))
    seen: set[str] = set()
    prefixes: set[str] = set()
    clean_cards: list[dict] = []
    for n, card in enumerate(cards, 1):
        if not isinstance(card, dict):
            probs.append(problem("shape", f"card {n} is not a mapping with id, human, agent, tags"))
            continue
        cid = card.get("id")
        label = cid if isinstance(cid, str) else f"#{n}"
        m = ID_RE.match(cid) if isinstance(cid, str) else None
        if not m:
            probs.append(problem("id", "id must look like ag-03 (2 to 4 letters, a dash, two digits)", label))
        else:
            prefixes.add(m.group(1))
            if cid in seen:
                probs.append(problem("id", f"the id {cid} appears twice", label))
            seen.add(cid)
        probs += text_problems(card.get("human"), "human", HUMAN_MAX, label)
        probs += text_problems(card.get("agent"), "agent", AGENT_MAX, label)
        tags = card.get("tags")
        if tags is None and not tags_required:
            tags = []
        lo = 1 if tags_required else 0
        if not isinstance(tags, list) or not lo <= len(tags) <= 4 or not all(isinstance(t, str) for t in tags):
            probs.append(problem("tags", "a card has 1 to 4 tags" if tags_required else "a card has at most 4 tags", label))
            tags = [t for t in (tags or []) if isinstance(t, str)] if isinstance(tags, list) else []
        for tag in tags:
            if not TAG_RE.match(tag):
                probs.append(problem("tags", f"tag '{tag}' must be a short lowercase word", label))
            elif tag not in BUILTIN_TAGS and tag not in clean_glossary:
                probs.append(problem("tags", f"tag '{tag}' has no glossary entry in plain words", label))
        clean_cards.append({"id": cid, "human": _face(card.get("human")), "agent": _face(card.get("agent")),
                            "tags": list(dict.fromkeys(tags))})
    if len(prefixes) > 1:
        probs.append(problem("id", f"all cards of a deck share one id prefix (found {', '.join(sorted(prefixes))})"))
    if probs:
        return None, probs
    deck = {k: doc[k] for k in ("schema", "deck", "name", "by", "license", "version", "faces", "mark")}
    for key in ("description", "voice", "area"):
        if doc.get(key):
            deck[key] = doc[key].strip()
    deck["name"] = deck["name"].strip()
    deck["glossary"] = clean_glossary
    deck["cards"] = clean_cards
    deck["prefix"] = next(iter(prefixes)) if prefixes else ""
    return deck, []


def load_text(text: str, slug: Optional[str] = None, tags_required: bool = True) -> dict:
    deck, probs = validate(parse_yaml(text), slug, tags_required)
    if deck is None:
        raise DeckError(summary(probs), probs)
    return deck


def summary(probs: list[dict], limit: int = 6) -> str:
    lines = [f"{p['card'] + ': ' if p.get('card') else ''}{p['message']} ({p['rule']})" for p in probs[:limit]]
    rest = len(probs) + problems_more(probs) - limit
    more = f"; and {rest} more" if rest > 0 else ""
    return "; ".join(lines) + more


def load_file(path: Path) -> dict:
    return load_text(Path(path).read_text(encoding="utf-8"), Path(path).stem)


def _load_dir(folder: Path, source: str) -> tuple[dict[str, dict], dict[str, str]]:
    decks: dict[str, dict] = {}
    broken: dict[str, str] = {}
    if not folder.is_dir():
        return decks, broken
    for path in sorted(folder.glob("*.yaml")):
        try:
            deck = load_file(path)
        except (DeckError, OSError, UnicodeDecodeError) as exc:
            broken[path.stem] = str(exc)
            continue
        except Exception as exc:  # one odd file never stops the plugin from loading
            broken[path.stem] = f"cannot read the deck ({type(exc).__name__})"
            continue
        deck["source"] = source
        decks[deck["deck"]] = deck
    return decks, broken


def _load_shipped() -> tuple[dict[str, dict], dict[str, str]]:
    shipped, broken = _load_dir(SHIPPED_DIR, "shipped")
    community, broken_c = _load_dir(COMMUNITY_DIR, "community")
    for slug, deck in community.items():
        if slug in shipped:
            broken_c[slug] = f"community deck '{slug}' has the name of a shipped deck"
            continue
        shipped[slug] = deck
    return shipped, {**broken, **broken_c}


# Loaded once with the code (a reload of the plugin reloads them): a broken shipped deck is a broken
# install, reported by the doctor and the decks list, never a crash mid-turn.
SHIPPED, SHIPPED_BROKEN = _load_shipped()


def reload_shipped() -> None:
    global SHIPPED, SHIPPED_BROKEN
    SHIPPED, SHIPPED_BROKEN = _load_shipped()


# --- switches (F13) ------------------------------------------------------------------------------

HERMES_DEFAULT = ("agent-unblock", "agent-unblock-own")  # 0.2: Hermes draws from the Agent deck alone by default
SEED_KEY = "hermes_seed"


def default_switch(source: str, slug: str = "") -> dict:
    """Drawing on for every deck; the Hermes switch (`auto`) on for the Agent deck (and its own copy) only."""
    return {"draw": True, "auto": slug in HERMES_DEFAULT and source != "imported"}


def legacy_switch(source: str) -> dict:
    """0.1's default, for the one-time seed: `auto` on for every deck but imported ones."""
    return {"draw": True, "auto": source != "imported"}


def read_switches(store: Store) -> dict:
    data = store.read_json(SWITCHES_FILE, default=None)
    if not isinstance(data, dict) or not isinstance(data.get("decks"), dict):
        return {"schema": SCHEMA, "decks": {}}
    return data


def _entry(switches: dict, slug: str) -> dict:
    entry = (switches.get("decks") or {}).get(slug)
    return entry if isinstance(entry, dict) else {}


def switch_for(switches: dict, slug: str, source: str) -> dict:
    entry = _entry(switches, slug)
    base = default_switch(entry.get("source", source), slug)
    return {"draw": bool(entry.get("draw", base["draw"])), "auto": bool(entry.get("auto", base["auto"]))}


def set_switch(store: Store, slug: str, draw: Optional[bool] = None, auto: Optional[bool] = None,
               source: Optional[str] = None) -> dict:
    with store.lock():
        data = read_switches(store)
        entry = dict(_entry(data, slug))
        if draw is not None:
            entry["draw"] = bool(draw)
        if auto is not None:
            entry["auto"] = bool(auto)
        if source is not None:
            entry["source"] = source
        data["decks"][slug] = entry
        data["schema"] = SCHEMA
        store.write_json(SWITCHES_FILE, data)
        return entry


def seed_hermes_switches(store: Store, legacy_decks: Any) -> bool:
    """Once per data folder (PLAN-v0.2 M2): write each deck's Hermes switch from 0.1's rule, so an update
    changes no deck Hermes drew from. 0.1 drew from a deck when its name (or the own copy that replaced
    it) was in `autodraw_decks` and its `auto` switch was on. A missing list means 0.1's default
    `["agent-unblock"]`; `[]` means none. True when this call wrote the seed."""
    data = read_switches(store)
    if data.get(SEED_KEY):
        return False
    names = legacy_decks if isinstance(legacy_decks, list) else ["agent-unblock"]
    names = [n for n in names if isinstance(n, str)]
    with store.lock():
        data = read_switches(store)
        if data.get(SEED_KEY):
            return False
        cat = catalog(store)
        listed: set[str] = set()
        for name in names:
            listed.add(name)
            deck = resolve(cat, name)
            if deck is not None:
                listed.add(deck["deck"])
        for slug, deck in cat["decks"].items():
            entry = dict(_entry(data, slug))
            old_auto = bool(entry.get("auto", legacy_switch(entry.get("source", deck["source"]))["auto"]))
            entry["auto"] = old_auto and slug in listed
            data["decks"][slug] = entry
        data[SEED_KEY] = {"at": _now_iso(), "from": names[:50]}
        data["schema"] = SCHEMA
        store.write_json(SWITCHES_FILE, data)
    return True


def _now_iso() -> str:
    from . import bridge

    return bridge.iso()


def forget_switch(store: Store, slug: str) -> None:
    with store.lock():
        data = read_switches(store)
        if data["decks"].pop(slug, None) is not None:
            store.write_json(SWITCHES_FILE, data)


# --- the merged catalog --------------------------------------------------------------------------

def taken_by(slug: str) -> Optional[str]:
    """The source of the shipped or community deck that holds this name, else None."""
    deck = SHIPPED.get(slug)
    return deck.get("source", "shipped") if deck is not None else None


# Parsed user deck files, keyed by path and checked against (device, inode, size, mtime, ctime): a
# draw reads the catalog, and parsing every file with the pure-Python YAML parser on every draw cost
# hundreds of milliseconds with a few own decks. ctime moves on every write, so an edit that keeps
# the size and puts the old mtime back is still seen.
_DECK_CACHE: "dict[str, tuple]" = {}
_DECK_CACHE_MAX = 256
_DECK_LOCK = threading.Lock()


def _deck_copy(deck: dict) -> dict:
    """A copy whose lists a caller may change without changing the cache (cards are shared and read
    only, like a shipped deck's)."""
    return {**deck, "glossary": dict(deck.get("glossary") or {}), "cards": list(deck.get("cards") or [])}


def _user_file(path: Path, slug: str) -> tuple[str, Any]:
    """("ok", deck) or ("broken", reason) for one user deck file, parsed only when it changed."""
    key = str(path)
    try:
        st = os.stat(path)
    except OSError as exc:
        return "broken", str(exc)
    stamp = (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)
    with _DECK_LOCK:
        hit = _DECK_CACHE.get(key)
    if hit is None or hit[0] != stamp:
        try:
            result: tuple[str, Any] = ("ok", load_text(path.read_text(encoding="utf-8"), slug, tags_required=False))
        except (DeckError, OSError, UnicodeDecodeError) as exc:
            result = ("broken", str(exc))
        except Exception as exc:  # one odd file never stops the other decks from drawing
            result = ("broken", f"cannot read the deck ({type(exc).__name__})")
        hit = (stamp, result)
        with _DECK_LOCK:
            _DECK_CACHE.pop(key, None)
            _DECK_CACHE[key] = hit
            while len(_DECK_CACHE) > _DECK_CACHE_MAX:
                _DECK_CACHE.pop(next(iter(_DECK_CACHE)))
    kind, value = hit[1]
    return (kind, _deck_copy(value)) if kind == "ok" else (kind, value)


def user_decks(store: Store, switches: Optional[dict] = None) -> tuple[dict[str, dict], dict[str, str]]:
    """The user's deck files: {slug: deck} and {slug: why it is not loaded}.

    A file whose name a shipped or community deck holds is not loaded: it is listed as broken with a
    hint to import it under another name. Two decks under one name would share its switch, its journal
    lines and learned weights, and a file placed by hand could replace the auto-draw deck."""
    switches = read_switches(store) if switches is None else switches
    decks: dict[str, dict] = {}
    broken: dict[str, str] = {}
    names = store.listdir(USER_DIR)
    folder = store.path(USER_DIR) if names else None
    for name in names:
        if not name.endswith(".yaml"):
            continue
        slug = name[:-5]
        if not SLUG_RE.match(slug):
            continue
        holder = taken_by(slug)
        if holder:
            broken[slug] = (f"the name '{slug}' belongs to a {holder} deck, so this file is not loaded; import it "
                            f"under another name to use it")
            continue
        try:
            path = folder / name  # a plain name from the listing of a folder already checked
            if path.is_symlink():  # a link must still point inside the data folder
                path = store.path(USER_DIR, name)
            kind, deck = _user_file(path, slug)
        except StoreError as exc:
            kind, deck = "broken", str(exc)
        if kind != "ok":
            broken[slug] = deck
            continue
        entry = _entry(switches, slug)
        deck["source"] = "imported" if entry.get("source") == "imported" else "own"
        decks[slug] = deck
    return decks, broken


def catalog(store: Store) -> dict:
    """{"decks": {slug: deck with source, switch, shadowed_by, copy_of}, "broken": {slug: reason}}.

    A shipped or community deck keeps its name: a user file with the same name (placed by hand, or
    one an update caught up with) is listed under "broken" with a rename hint, never drawn in its
    place. New imports and saves may not take a shipped name either (the editor refuses them)."""
    switches = read_switches(store)
    own, broken = user_decks(store, switches)
    out: dict[str, dict] = {}
    for slug, deck in SHIPPED.items():
        out[slug] = dict(deck)
    for slug, deck in own.items():
        out[slug] = dict(deck)
    for slug, deck in out.items():
        deck["switch"] = switch_for(switches, slug, deck["source"])
        base = slug[: -len(OWN_SUFFIX)] if slug.endswith(OWN_SUFFIX) else None
        if base and base in SHIPPED and out.get(base, {}).get("source") in ("shipped", "community"):
            deck["copy_of"] = base
            out[base]["shadowed_by"] = slug
    return {"decks": out, "broken": {**SHIPPED_BROKEN, **broken}}


def resolve(cat: dict, slug: str) -> Optional[dict]:
    """The deck to draw from for a name: an own copy replaces its shipped original."""
    decks = cat["decks"]
    deck = decks.get(slug)
    if deck is None and not slug.endswith(OWN_SUFFIX):
        return None
    if deck is not None and deck.get("shadowed_by"):
        return decks.get(deck["shadowed_by"], deck)
    return deck


def drawable(cat: dict, slugs: Optional[list] = None, for_auto: bool = False) -> list[dict]:
    """Decks a draw may use: named ones (resolved), else every deck switched on; shadowed originals
    are skipped. `for_auto` also requires the deck's auto switch."""
    decks = cat["decks"]
    if slugs:
        chosen = []
        for slug in slugs:
            deck = resolve(cat, slug)
            if deck is not None and deck not in chosen:
                chosen.append(deck)
    else:
        chosen = [d for d in decks.values() if not d.get("shadowed_by")]
    out = []
    for deck in chosen:
        sw = deck["switch"]
        if not sw["draw"] and not slugs:
            continue
        if for_auto and not sw["auto"]:
            continue
        out.append(deck)
    return out


def hermes_decks(cat: dict) -> list[dict]:
    """The decks Hermes draws from when stuck: Hermes switch (`auto`) on, not replaced by an own copy,
    with at least one `auto` card. The Draw switch is the person's and does not count here."""
    return [d for d in cat["decks"].values()
            if d["switch"]["auto"] and not d.get("shadowed_by") and any("auto" in c["tags"] for c in d.get("cards") or [])]


def find_card(deck: dict, card_id: str) -> Optional[dict]:
    for card in deck.get("cards") or []:
        if card["id"] == card_id:
            return card
    return None


def explain_tags(deck: dict, tags: list) -> list[dict]:
    """"Why this card?" in plain words (F16)."""
    glossary = deck.get("glossary") or {}
    return [{"tag": t, "means": BUILTIN_TAGS.get(t) or glossary.get(t, "")} for t in tags]


def deck_summary(deck: dict) -> dict:
    """A deck without its cards, for lists."""
    keys = ("deck", "name", "by", "license", "version", "mark", "description", "area", "source", "switch",
            "shadowed_by", "copy_of", "prefix")
    out = {k: deck[k] for k in keys if k in deck}
    cards = deck.get("cards") or []
    out["cards"] = len(cards)
    out["auto_cards"] = sum(1 for c in cards if "auto" in c["tags"])
    out["human_cards"] = sum(1 for c in cards if "human" in c["tags"])
    return out
