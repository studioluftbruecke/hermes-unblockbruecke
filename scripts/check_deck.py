#!/usr/bin/env python3
"""Check a deck file before you propose it (F14): the plugin loader's rules.

    python3 scripts/check_deck.py my-deck.yaml [more.yaml ...]

Needs `ruamel.yaml` (Hermes ships it; outside Hermes: `pip install ruamel.yaml`). Prints `ok` per
file, or every rule a card breaks, and exits 1 when any file fails. Whether a card copies or closely
paraphrases another work (the original Oblique Strategies among them) is not checked here: the
maintainer checks that when the deck is proposed.
"""
from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = "unblockbruecke_check_deck"
NOTE = ("note: this script checks the loader's rules only; the originality check against the original Oblique "
        "Strategies is run by the maintainer when you propose the deck")


def _decks():
    if PKG not in sys.modules:
        spec = importlib.util.spec_from_file_location(PKG, ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[PKG] = module
        spec.loader.exec_module(module)
    return importlib.import_module(f"{PKG}.decks")


def check_file(path: Path) -> list[dict]:
    """Every problem in one deck file (at most the loader's cap listed; `problems_more` counts the rest)."""
    decks = _decks()
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return [{"rule": "read", "card": None, "message": f"cannot read the file: {exc}"}]
    try:
        doc = decks.parse_yaml(text)
    except decks.DeckError as exc:
        return [{"rule": exc.code, "card": None, "message": str(exc)}]
    _deck, probs = decks.validate(doc, path.stem)
    return probs


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__.strip().splitlines()[2].strip())
        return 2
    decks = _decks()
    failed = 0
    for name in argv:
        path = Path(name)
        try:
            probs = check_file(path)
        except Exception as exc:  # report, never a traceback: the contributor needs the file name
            probs = [{"rule": "internal", "card": None, "message": f"the check could not read this deck ({type(exc).__name__})"}]
        if probs:
            failed += 1
            total = len(probs) + decks.problems_more(probs)
            print(f"{path}: {total} problem(s)")
            for p in probs[:decks.MAX_PROBLEMS]:
                where = f"{p['card']}: " if p.get("card") else ""
                print(f"  - {where}{p['message']} [{p['rule']}]")
            if total > decks.MAX_PROBLEMS:
                print(f"  - and {total - decks.MAX_PROBLEMS} more")
        else:
            print(f"{path}: ok")
    print(NOTE)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
