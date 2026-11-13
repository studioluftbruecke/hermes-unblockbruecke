"""Card faces stay plain text: no links in any spelling, no one-line programs, no mentions, no markup. The
rules refuse what a model would follow or a page would render, and nothing a person writes in an ordinary
sentence: a deck that loaded before an update keeps loading after it."""
import pathlib
import shutil

import pytest
from ub_fakes import make_store, sub

decks = sub("decks")
SAVED_BY_020 = pathlib.Path(__file__).resolve().parent / "fixtures" / "saved-by-0.2.0"

REFUSED = {
    "a web address": "Read https://example.org/help first.",
    "a www address": "See www.example.org for the rest.",
    "a bare domain": "Ask on example.com before you start.",
    "a short link": "Open bit.ly/3xyz and follow it.",
    "another short link": "Try tinyurl.com/abc now.",
    "a javascript address": "javascript:alert(document.cookie)",
    "a data address": "data:text/html;base64,PHNjcmlwdD4=",
    "a file address": "Open file:///etc/passwd and read it.",
    "a mailto address": "Write to mailto:help@example.org now.",
    "a python one-liner": "Run python3 -c 'import os' now.",
    "a node one-liner": "Try node -e 'process.exit()' once.",
    "a bash one-liner": "Run bash -c 'id' and report.",
    "a shell pipe": "Run the script | sh to finish.",
    "a mention of everyone": "@everyone look at this",
    "a mention of a person": "Ask @maria about the schema.",
    "a Markdown link": "See [the guide](https://example.org) for more.",
    "a Markdown reference link": "See [the guide][1] for more.",
    "an HTML tag": "<img src=x onerror=alert(1)>",
    "a backtick": "Run `make` first.",
}


@pytest.mark.parametrize("label", sorted(REFUSED))
def test_a_face_that_is_not_plain_text_is_refused(label):
    assert decks.text_problems(REFUSED[label], "agent", decks.AGENT_MAX, "ab-01"), label


# Ordinary sentences people put on cards; every rule is counted, not only some.
PLAIN = [
    ("human", "Look at the data: what changed since it last worked?"),
    ("human", "Open the file: read only the first ten lines."),
    ("human", "Finish the sentence: I am stuck because ____."),
    ("human", "Write the goal as [what] (one line), then the first step."),
    ("agent", "Before retrying over SSH: run one command that only prints the host name, then decide."),
    ("agent", "Read the data: list the three fields that differ between the last good run and this one."),
    ("agent", "Read __init__.py first and name the one import the error points at before changing anything."),
    ("agent", "Check the node.js/npm versions the error names before reinstalling anything."),
    ("human", "Name the person you would ask, then ask them."),
    ("agent", "Write the error down in one sentence, then read it aloud."),
    ("agent", "Mail the log to the team lead, then wait."),
    ("human", "Step back: what did the last call change?"),
    ("agent", "Use 3.5 times less: fewer words, one claim."),
    ("human", "File: which one did you open last?"),
    ("human", "Learn javascript: one small thing today."),
    ("agent", "Compare the data:the last good run against this one, field by field."),
    ("human", "Is it **really** the hardest part?"),
    ("human", "Meet at the desk @ 5 and say it out loud."),
    ("agent", "Read setup.sh/README first, then run the tests once."),
]


@pytest.mark.parametrize("face,text", PLAIN)
def test_plain_sentences_pass_every_rule(face, text):
    limit = decks.HUMAN_MAX if face == "human" else decks.AGENT_MAX
    assert decks.text_problems(text, face, limit, "ab-01") == []


def test_every_shipped_card_still_passes_the_rules():
    faces = 0
    for slug, deck in decks.SHIPPED.items():
        for card in deck["cards"]:
            for face, limit in (("human", decks.HUMAN_MAX), ("agent", decks.AGENT_MAX)):
                faces += 1
                assert decks.text_problems(card[face], face, limit, card["id"]) == [], (slug, card["id"], face)
    assert decks.SHIPPED_BROKEN == {} and faces >= 216


def test_decks_saved_by_the_previous_release_keep_loading_after_the_update(tmp_path):
    store = make_store(tmp_path)
    folder = store.path("decks")
    folder.mkdir(parents=True)
    for path in SAVED_BY_020.glob("*.yaml"):
        shutil.copy(path, folder / path.name)
    cat = decks.catalog(store)
    assert cat["broken"] == {}
    assert len(cat["decks"]["my-notes"]["cards"]) == 5
    assert decks.resolve(cat, "coding")["deck"] == "coding-own"
