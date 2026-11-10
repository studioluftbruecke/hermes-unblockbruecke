# UnblockBrücke Cards

Decks of short cards that get you unstuck, and get your Hermes agent unstuck too. Every card has
two faces: a playful line for you, and one concrete instruction for an agent. Draw one when you are
blocked. Switch on auto-draw, and Hermes draws one for itself after three failed tool calls in a
row.

A free, playful member of the Studio Luftbrücke plugin family.

The cards are written new for Hermes, in the spirit of Brian Eno and Peter Schmidt's Oblique
Strategies. The original Oblique Strategies are not included.

## Where it shows up in Hermes Desktop

- **Cards** page (a sidebar row you can hide in the plugin's settings), with three views:
  - **Table:** pick a deck, **Draw**, turn the card over (click it or press F). **Use in chat** puts
    the card into your message draft, **Ask Hermes** starts a chat about it, and **Why this card?**
    explains its tags.
  - **Decks:** every deck with a **Draw** and an **Auto** switch. Write your own decks and cards,
    preview each change before you save it, restore an earlier version, import and export YAML
    files.
  - **Journal:** every draw, who drew it, what happened next, and **Helped** / **Not now**.
- **Card of the day** in the status bar. Click it for the card, **Another**, or **Open decks**.
  When Hermes draws a card in the chat you have open, the chip says so for half a minute.
- **Command palette:** "Draw a card", "Draw from <deck>", "Open decks". The shortcut
  ⌘⌥U (Ctrl+Alt+U) draws a card; you can rebind it in Desktop's keyboard shortcuts.
- **Cards in chat:** `/card` or `/card coding` in any chat draws without a model call, and your
  agent can show a card inline with `::card{deck="coding" id="co-03"}`.
- **Settings ▸ Plugins ▸ UnblockBrücke Cards:** auto-draw and its threshold, the decks Hermes may
  draw from, card of the day, learning, show in sidebar; a **Decks and learning** page with the
  deck switches and a **Reset learning** button.

## Decks

| Deck | For | Example |
| --- | --- | --- |
| Agent unblock (24) | Hermes and other agents stuck on an error | "What did all three attempts believe?" / "Name the one assumption your last three attempts shared, then test that assumption directly before changing anything else." |
| Human unblock (24) | Creative and work blocks, and breaks | "Make the worst version first." |
| Coding, Design, Shaders, Writing (8 each) | A craft that will not move | "Grey tells the truth." |

Decks learn from your ratings: a card you mark **Helped** comes up a little more often, never so
much that the others disappear. **Reset learning** starts the counts again and keeps the journal.

## Auto-draw (off by default)

When it is on and tool calls fail in a row in one turn (three by default, the setting
`autodraw_threshold`), the failing result that reaches the count carries one card from the decks you
picked (Agent unblock unless you change it; an empty list means no deck). Hermes still sees the call as
failed, and its own loop warnings still apply: the card adds a direction, it never hides an error.
At most one card per turn. When nobody is at the keyboard (scheduled jobs, `hermes chat -q`), cards
that ask a person something are skipped and the agent cannot change your decks.

## Your agent

| Tool | What it does |
| --- | --- |
| `unblockbruecke_card` | Draw a card, list decks, show a card, read the journal, rate a draw |
| `unblockbruecke_decks` | Edit decks: preview a change, save it with a version, restore, switch, import, export |

The bundled skill `unblockbruecke:unblockbruecke` tells the agent when to offer a card and how to
coach with one. With Eselsbrücke installed, a break the agent starts can show a human card.

## Share a deck

Propose a deck as a pull request to this repository; `CONTRIBUTING.md` explains the file and the
rules, and `scripts/check_deck.py` checks it. Every deck is reviewed before it ships, and decks are
plain text only: no links, no code, no HTML.

## Disclosures

- **Network calls:** none. The Desktop half talks only to this plugin's routes on your own Hermes
  backend (`/api/plugins/unblockbruecke/...`).
- **Files:** everything lives in the plugin's data folder
  (`<profile>/plugin-data/agent-plugin-unblockbruecke-…`): your decks and their last 20 versions,
  the deck switches, and the journal of draws (one JSONL file per month, only ever appended). The
  agent writes a deck file elsewhere only when it exports to a path you name.
- **Agent context:** with auto-draw on, the text of one card from the decks you allow is added to a
  failing tool result, so the model reads it. A card the agent draws on request enters its context
  the same way.
- **Shell commands, child processes, scheduled jobs:** none.
- **Bundled data:** the six decks in `data/decks/`. The plugin contains no text of the original
  Oblique Strategies and no data derived from it; the maintainer checks every deck against them
  before it ships. `desktop/plugin.js` (62 KB) is built from `desktop/src` by `desktop/build/`
  (`npm ci && node build.mjs`). Hermes' install scan says `safe`; its medium findings are esbuild's
  character escapes in the bundle and the word `sudo` in the rule that refuses it in cards.
- **Credentials:** none.
- **Telemetry:** none.

## Install

```bash
hermes plugins install studioluftbruecke/hermes-unblockbruecke
hermes plugins enable unblockbruecke
```

Then switch on the Desktop half in Capabilities → Plugins.

## License

Code: MIT, see `LICENSE`. Deck texts: CC BY 4.0 for the shipped decks, CC BY 4.0 or CC0 for
community decks, see `DECKS-LICENSE.md`.
