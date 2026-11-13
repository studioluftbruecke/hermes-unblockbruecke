"""Names and copy: the copy budgets, the one name, the short deck names and marks.

Red on 0.1.0 (a 340-character manifest, setting texts up to 414 characters, a tool head without
"stuck", a 751-word skill, the long deck names) and on 0.1.4 (`origin/main` when 0.2 started: a
614-word skill, the long deck names and the suit marks, the old card-of-the-day and learning texts).
"""

import re

from ruamel.yaml import YAML

from ub_fakes import ROOT, sub

SKILL_WORDS_MAX = 400
ONE_LINER = ("Cards to unblock yourself or your agent, drawn by you when you are stuck and by Hermes when its "
             "tool calls keep failing.")
# The settings' labels and descriptions, word for word.
SETTING_TEXTS = {
    "autodraw": ("Hermes draws when stuck", "After 3 failed tool calls out of the last 5, Hermes gets one card with a next "
                                            "move. The call still counts as failed."),
    "autodraw_threshold": ("Failed calls before a card", "How many failed calls bring a card (2 to 6), counted over the "
                                                         "last few calls of a turn."),
    "card_of_day": ("Card of the day", "One card for you each day in the status bar."),
    "learning": ("Decks learn", "Cards you mark as helped come up a little more often. None disappears."),
}
# Short deck names ("Human", "Coding", ...) and a glyph per deck that names its subject.
DECKS = {"human-unblock": ("Human", "person"), "coding": ("Coding", "code"), "writing": ("Writing", "pencil"),
         "design": ("Design", "shapes"), "shaders": ("Shaders", "sphere"), "agent-unblock": ("Agent", "robot")}


def manifest():
    return YAML(typ="safe", pure=True).load((ROOT / "plugin.yaml").read_text(encoding="utf-8"))


def test_manifest_description_is_the_one_liner_within_200():
    desc = manifest()["description"]
    assert len(desc) <= 200
    assert desc == ONE_LINER + " Original decks, your own decks, local files, no account."


def test_every_setting_description_within_140():
    over = {k: len(v["description"]) for k, v in manifest()["config_schema"].items() if len(v["description"]) > 140}
    assert over == {}


def test_setting_texts_follow_the_settings_table():
    schema = manifest()["config_schema"]
    for key, (label, description) in SETTING_TEXTS.items():
        assert (schema[key]["label"], schema[key]["description"]) == (label, description), key
    assert list(schema) == ["autodraw", "autodraw_threshold", "card_of_day", "learning", "show_in_statusbar"]


def test_card_tool_head_says_draw_and_stuck():
    head = sub("tools.card").SCHEMA["description"][:78]
    assert "draw" in head and "stuck" in head
    assert head.startswith("draw a card when you or the user are stuck; also decks, show, journal, rate.")


def test_skill_at_most_400_words_and_keeps_the_rules():
    text = (ROOT / "skills" / "unblockbruecke" / "SKILL.md").read_text(encoding="utf-8")
    assert len(text.split()) <= SKILL_WORDS_MAX, len(text.split())
    for rule in ("never an order", "Never draw in a loop", "Never rate", "still failed", "confirm", "undo"):
        assert rule in text, rule
    assert "a card has 1 to 4" not in text.lower() and "at most 90 characters" not in text, "deck file rules left the skill"


def test_shipped_decks_have_short_names_and_glyph_marks():
    shipped = sub("decks").SHIPPED
    assert {slug: (shipped[slug]["name"], shipped[slug]["mark"]) for slug in DECKS} == DECKS


def test_the_feature_has_one_phrase_where_a_person_reads():
    """'Hermes draws when stuck' everywhere a person reads; the old words 'auto-draw' and 'Auto' are gone
    from the texts the page shows (the tag hover, the import note, the settings form)."""
    decks = sub("decks")
    assert "auto-draw" not in decks.BUILTIN_TAGS["auto"].lower()
    texts = [v["label"] + " " + v["description"] for v in manifest()["config_schema"].values()]
    assert not [t for t in texts if re.search(r"(?i)auto-draw|\bAuto\b", t)]
    editor = (ROOT / "editor.py").read_text(encoding="utf-8")
    assert "off for auto-draw" not in editor


def test_desktop_src_has_no_old_name():
    src = "\n".join(p.read_text(encoding="utf-8") for p in sorted((ROOT / "desktop" / "src").glob("*.js")))
    assert "UnblockCards" not in src
    assert "UnblockBrücke" not in src
    assert not re.search(r"label: '(Cards)'", src)


def test_plugin_texts_use_the_new_names():
    texts = [p for p in ROOT.rglob("*") if p.is_file() and p.suffix in {".py", ".md", ".yaml", ".json", ".mjs"}
             and p.name != "CHANGELOG.md" and "node_modules" not in p.parts and p.parent.name != "tests"]
    stale = [str(p.relative_to(ROOT)) for p in texts if re.search(r"UnblockBr(ü|ue)cke|UnblockCards", p.read_text(encoding="utf-8"))]
    assert stale == []


def test_show_in_statusbar_keeps_its_texts():
    """The fifth setting the page writes keeps its label and default."""
    schema = manifest()["config_schema"]
    assert schema["show_in_statusbar"]["label"] == "Show in status bar"
    assert schema["show_in_statusbar"]["default"] is True
    assert "show_in_sidebar" not in schema, "retired in 0.1.4: the switch is on the plugin's own page"
