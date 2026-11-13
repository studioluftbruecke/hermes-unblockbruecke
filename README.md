# Unblockbrücke

Cards to unblock yourself or your agent.

Every card has two faces: a short line for you on the front, and a next move for Hermes on the
back. Draw one when you are blocked. Switch on **Hermes draws when stuck**, and Hermes gets a card
after 3 failed tool calls out of the last 5 in one turn. A free, playful member of the Studio
Luftbrücke plugin family.

The cards are written new for Hermes, in the spirit of Brian Eno and Peter Schmidt's Oblique
Strategies. The original Oblique Strategies are not included.

## What it does

- **One page, three tabs.** **Draw** is for you, **Hermes** is for your agent, **Decks** holds the
  library and the editor.
- **Draw.** The deck chips stand in one fixed order: Human, Coding, Writing, Design, Shaders, Agent,
  All. Exactly one is pressed, Human on a first run. A press picks where the next card comes from
  and draws nothing. **Draw** deals a card. Click it (or press F) to turn it to its back, headed
  "For Hermes". **Draw another** (or D) deals the next one. Under the card stand your earlier draws:
  the card before asks **Helped** or **Not this time** once. **Cards that helped** lists the cards
  you marked, with **Reset learning**.
- **Pass it to Hermes.** One message with the card, its line and its back goes into the chat in
  focus, or into a new chat. Hermes can start the move without looking the card up. Nothing is
  sent: you press send.
- **Hermes draws when stuck (off by default).** When 3 of the last 5 tool calls in one turn failed,
  the failing result that makes the count carries one card. One card per turn at most. The call
  still counts as failed: the card adds a direction and never hides an error. Hermes draws only
  cards written for it (tagged `auto`), from the decks whose Hermes switch is on: the Agent deck out
  of the box. When the error says a server could not be reached, a card about reframing the
  problem comes first.
- **The Hermes tab.** The switch with one sentence and an example card, **Failed calls before a
  card** (2 to 6), a switch for each deck that has cards written for Hermes, and **What Hermes drew
  lately**: where the turn ran (Desktop chat, Kanban task, Cron job, CLI, Delegated task) and what
  the next call did, as a fact. Draws in runs nobody watched show up there too.
- **The chip in the status bar.** It carries the card of the day as one line. Click it for the card,
  **Pass it to Hermes**, **Another** and **Open Unblockbrücke**. When Hermes draws a card in the chat
  you are in, the chip shows that card's line and a dot until you click it, the next turn starts or
  another chat gets focus. Its popover then asks **Helped** or **Not this time**.
- **A line under the reply.** On a turn where Hermes drew a card, one line follows the reply: the
  card itself in Desktop, a plain line on other surfaces.
- **Six decks, 108 cards.** Agent (24, 19 of them written for Hermes), Human (28), Design, Shaders
  and Writing (16 each), and Coding (8). Cards you mark **Helped** come up a little more often; none
  disappears.
- **Your own decks.** On the Decks tab, **New deck** and **New card**. Edits in your own decks save
  at once, and **Undo** takes a save back. Tags are optional there. A shipped deck has **Make my own
  copy**; your copy then takes its place. **Versions**, **Export** and **Import a deck file** are
  there too. One **Draw** switch per deck decides whether it shows on the Draw tab, the chip and the
  palette. When Hermes edits a deck, you see a preview and confirm it first.
- **Cards everywhere.** `/card` in any chat (no model call), the command palette (**Draw a card**,
  **Draw from <deck>**, **Open Unblockbrücke**), ⌘⌥U (Ctrl+Alt+U), and inline cards with
  `::card{deck="coding" id="co-03"}`.

## Install and update

```bash
hermes plugins install https://github.com/studioluftbruecke/hermes-unblockbruecke --enable
```

Hermes Desktop loads the page, the status bar chip and the settings page (`desktop/plugin.js`) from
the computer it runs on, never from a Hermes on a server. With Hermes on a server, install and
update the plugin in both places, on the same version. With Hermes and Desktop on one computer, one
install covers both.

| Where | Install | Update |
| --- | --- | --- |
| Server: tools, hooks, routes | `hermes -p <profile> plugins install https://github.com/studioluftbruecke/hermes-unblockbruecke --enable` | `hermes -p <profile> plugins update unblockbruecke` |
| Desktop computer: page, status bar chip and settings page | `hermes plugins install https://github.com/studioluftbruecke/hermes-unblockbruecke` | `hermes plugins update unblockbruecke` |

- After either step on the Desktop computer: Capabilities → Plugins → Rescan. A new install's
  Desktop half arrives switched off; switch it on there.
- No Hermes on the Desktop computer: Capabilities → Plugins → Install from Git with the URL; to
  update, the same with Advanced → Force reinstall. Desktop's Update button updates the server only.
- After an update on the server, Desktop chats and the plugin's routes keep the old code: in
  Capabilities → Plugins, switch **Agent in <profile>** off and on, then start a new chat.
- Same version in both places? Compare the Version column of `hermes plugins list` on the Desktop
  computer and `hermes -p <profile> plugins list` on the server.
- The sidebar switch and position on the plugin's settings page are kept per Desktop, so a second
  computer starts with the defaults.

## First use

1. Install the plugin and switch its Desktop half on (above).
2. Open **Unblockbrücke** in the sidebar, or **Open Unblockbrücke** in the command palette or the
   chip's popover, and press **Draw**. Or type `/card` in any chat.
3. To let Hermes draw for itself, switch on **Hermes draws when stuck** on the **Hermes** tab.

## Settings

Settings ▸ Plugins ▸ Unblockbrücke opens a short page: **Open Unblockbrücke**, the **Sidebar** block
(**Show in the sidebar** and **Position**, 53 by default; lower numbers sit higher, Kanban is 50)
and, with Hermes on another computer, the update line. The settings below sit beneath it in **Agent
settings**. The Hermes tab writes the first two as well; both places read the same value.

| Setting | Default | What it does |
| --- | --- | --- |
| `autodraw` | off | Hermes draws when stuck: after 3 failed tool calls out of the last 5 in a turn, Hermes gets one card |
| `autodraw_threshold` | 3 | Failed calls that bring a card (2 to 6), counted over the last that many calls plus 2 |
| `card_of_day` | on | One card a day on the chip in the status bar |
| `learning` | on | Cards rated Helped come up a little more often; none disappears |
| `show_in_statusbar` | on | The chip in the status bar. Right-clicking the status bar also hides it, per Desktop |

`autodraw_per_turn` and `autodraw_decks` are gone since 0.2.0: Hermes gets one card per turn at
most, and each deck's Hermes switch decides. On the first read after the update, a stored
`autodraw_decks` list sets those switches once.

When nobody is at the keyboard (scheduled jobs, `hermes chat -q`), cards that ask a person
something are skipped, the agent cannot change your decks, and the settings route refuses to save.

## Your agent

| Tool | What it does |
| --- | --- |
| `unblockbruecke_card` | Draw a card when you or the user are stuck; list decks, show a card, read the journal, rate a draw |
| `unblockbruecke_decks` | Edit decks: preview a change, save it with a version, restore, switch, import, export |

The bundled skill `unblockbruecke:unblockbruecke` tells the agent when to offer a card and how to
coach with one.

## Disclosures

- **Network calls:** none. The Desktop half talks only to this plugin's routes on your own Hermes
  backend (`/api/plugins/unblockbruecke/...`).
- **Files:** everything lives in the plugin's data folder
  (`<profile>/plugin-data/agent-plugin-unblockbruecke-…`): your decks and their last 20 versions,
  the deck switches, and the journal of draws (one JSONL file per month, only ever appended). A row
  for one of Hermes' draws names where the turn ran and whether the next call failed. The agent
  writes a deck file elsewhere only when it exports to a path you name.
- **Settings writes:** the page saves settings through its own route,
  `POST /api/plugins/unblockbruecke/setting`. It takes one key per call from a fixed list
  (`autodraw`, `autodraw_threshold`, `card_of_day`, `learning`, `show_in_statusbar`) and refuses
  every other key, so no secret can pass through it. It writes with Hermes' own plugin-settings
  writer into the profile's `config.yaml`. It refuses to save in unattended runs (scheduled jobs and
  single-query runs).
- **Agent context:** with **Hermes draws when stuck** on, about 300 characters (the card's back, one
  sentence and a draw id) are added to the failing tool result, so the model reads them. A card the
  agent draws on request enters its context the same way.
- **Reply line:** the plugin registers a `transform_llm_output` hook. On a turn where it attached a
  card to a tool result, it adds one line after the reply: `::card{...}` in Desktop, which the page
  shows as the card, and a plain line naming the card on other surfaces. The line is stored with the
  reply. It never holds the stream back, and other replies stay as they are.
- **Shell commands, child processes, scheduled jobs:** none.
- **Bundled data:** the six decks in `data/decks/`. The plugin contains no text of the original
  Oblique Strategies and no data derived from it; the maintainer checks every deck against them
  before it ships. `desktop/plugin.js` (72 KB) is built from `desktop/src` by `desktop/build/`
  (`npm ci && node build.mjs`). Hermes' install scan says `safe`; its medium findings are esbuild's
  character escapes in the bundle, the word `sudo` in the rule that refuses it in cards, and the
  tests that run node.
- **Credentials:** none.
- **Telemetry:** none.

## Uninstall

```bash
hermes plugins remove unblockbruecke
```

On a server, run it there with `-p <profile>` and on the Desktop computer. Your decks and journal stay
in the profile's plugin data folder; delete that folder to remove them too.

## Contributing

Propose a deck or a fix as a pull request: [`CONTRIBUTING.md`](CONTRIBUTING.md) explains the deck
file, the rules and how pull requests land. `scripts/check_deck.py` checks a deck.

## License

Code: MIT, see `LICENSE`. Deck texts: CC BY 4.0 for the shipped decks, CC BY 4.0 or CC0 for
community decks, see `DECKS-LICENSE.md`.
