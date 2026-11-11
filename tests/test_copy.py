"""M1 'Names and copy' (PLAN-v0.2): the copy budgets and the one name per level, as 0.1.3 ships them.

On 0.1.0/0.1.1 this fails on the copy budgets: a 340-character manifest description, setting texts up
to 414 characters, "draw, decks, show, ..." without "stuck" in the catalog head. On 0.1.2 it fails on
the names: 0.1.3 shows Unblockbrücke on the sidebar row, the page, the settings entry and the card.

The skill budget is relaxed on purpose: the plan's 400 words would drop the deck change format and the
card rules the agent needs to edit decks, so the skill keeps every instruction and is held to the size
it was cut to here (751 -> about 614 words).
"""

import re

from ruamel.yaml import YAML

from ub_fakes import ROOT

SKILL_WORDS_MAX = 620
ONE_LINER = ("Cards to unblock yourself or your agent, drawn by you when you are stuck and by Hermes when its "
             "tool calls keep failing.")


def manifest():
    return YAML(typ="safe", pure=True).load((ROOT / "plugin.yaml").read_text(encoding="utf-8"))


def test_manifest_description_is_the_one_liner_within_200():
    desc = manifest()["description"]
    assert len(desc) <= 200
    assert desc == ONE_LINER + " Original decks, your own decks, local files, no account."


def test_every_setting_description_within_140():
    over = {k: len(v["description"]) for k, v in manifest()["config_schema"].items() if len(v["description"]) > 140}
    assert over == {}


def test_autodraw_text_still_says_in_a_row():
    """No behaviour change since 0.1.2: the trigger is N failed calls in a row, not '3 of the last 5'."""
    schema = manifest()["config_schema"]
    assert "in a row" in schema["autodraw"]["description"]
    assert "in a row" in schema["autodraw_threshold"]["description"]
    assert "last 5" not in schema["autodraw"]["description"]


def test_card_tool_head_says_draw_and_stuck():
    src = (ROOT / "tools" / "card.py").read_text(encoding="utf-8")
    first = re.search(r'"description": \(\s*"([^"]*)"', src).group(1)
    assert "draw" in first[:78] and "stuck" in first[:78]


def test_skill_size():
    words = len((ROOT / "skills" / "unblockbruecke" / "SKILL.md").read_text(encoding="utf-8").split())
    assert words <= SKILL_WORDS_MAX


def test_desktop_src_uses_the_new_names():
    src = "\n".join(p.read_text(encoding="utf-8") for p in sorted((ROOT / "desktop" / "src").glob("*.js")))
    assert "UnblockCards" not in src
    assert "UnblockBrücke" not in src
    assert not re.search(r"label: '(Cards)'", src)
    assert "label: 'Unblockbrücke'" in src
    assert "id: 'page', area: ROUTES_AREA, title: 'Unblockbrücke'" in src
    assert "registerSettingsPage({ id: 'cards', title: 'Unblockbrücke'" in src
    assert "h('h1', null, 'Decks and learning')" in src
    assert "h('span', { className: 'bw' }, 'Unblockbrücke')" in src
    assert "'Cards to unblock yourself or your agent.'" in src


def test_plugin_texts_use_the_new_names():
    texts = [p for p in ROOT.rglob("*") if p.is_file() and p.suffix in {".py", ".md", ".yaml", ".json", ".mjs"}
             and p.name != "CHANGELOG.md" and "node_modules" not in p.parts and p.parent.name != "tests"]
    stale = [str(p.relative_to(ROOT)) for p in texts if re.search(r"UnblockBr(ü|ue)cke|UnblockCards", p.read_text(encoding="utf-8"))]
    assert stale == []
