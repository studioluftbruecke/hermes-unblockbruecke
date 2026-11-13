# Changelog

## 0.2.2

No change to how the plugin works; updating is optional.

- A GitHub Actions job rebuilds `desktop/plugin.js` from `desktop/src` and fails when it differs from
  the committed file, so the Desktop bundle can be trusted without rebuilding it by hand.

## 0.2.1

A review round on security and correctness before the catalog's next review. Update both halves: the plugin where Hermes runs and the one Hermes Desktop loads.

- A small deck file built from YAML aliases is refused at once instead of hanging the import.
- Deck names, card ids, tags and op ids with a trailing line break are refused.
- Card text rules also refuse short links (`bit.ly/x`), `javascript:`, `mailto:`, `file:` and `data:`
  addresses, one-line programs (`python3 -c`) and @mentions. Ordinary sentences such as "Look at the
  data: what changed?" still pass, so a deck saved before the update keeps loading.
- A deck file with a key the plugin does not know still loads; the deck list, the page and an import
  name that key and say that a save does not keep it.
- Auto-draw counts a failed call from the status Hermes passes to the hook, except where Hermes' own
  loop does not count it either (a repeat its guardrail refused, a terminal command that exited 0).
- Saving a setting on the page runs `hermes config set` in a short child process. Hermes' refusals
  still hold there (a managed install, a key an administrator pinned) and answer "not allowed".
- When this Hermes version cannot say whether a person is present, deck writes are refused with one
  sentence that says so, also inside the plugin host.
- The line naming a drawn card is no longer added to replies of scheduled jobs, webhooks, the API
  server or single-query runs.
- The page's tabs switch through Desktop's own navigation.
- Unknown deck names are cut short in error messages.
- README: install from the catalog first, which edits the agent can make in one turn, that the
  agent's import reads any path, which failed calls auto-draw never sees, and that another plugin
  rewriting replies competes with the card line.

## 0.2.0

- One page with three tabs: **Draw** for you, **Hermes** for your agent, **Decks** for the library
  and the editor. The table, the journal, the deck list with descriptions, "Show agent face",
  "Use in chat", "Ask Hermes" and "Why this card?" are gone. Old links to the table and the
  journal open Draw and Hermes.
- Draw: the deck chips stand in one fixed order (Human, Coding, Writing, Design, Shaders, Agent,
  All) and never move or fold. Exactly one is pressed, Human on a first run. A press picks the deck
  for the next draw and draws nothing.
- The card: the front shows the line and the deck, with no face label. The back is headed "For
  Hermes"; a click (or F) turns the card. The corner shows the deck's mark and the card number
  (`05`, not `co-05`).
- **Pass it to Hermes** drafts one message into the chat in focus, or a new chat: the card, its
  line and its back, so Hermes can start the move without looking the card up. It never sends.
- Under the card stand your earlier draws; the card before asks **Helped** or **Not this time**
  once. **Cards that helped** lists the cards you marked, with **Reset learning**.
- Deck names: Human unblock is now **Human**, Agent unblock is now **Agent**. Each shipped deck has
  a mark that shows what it is about: a person, two chevrons, a pencil, three shapes, a shaded
  sphere, a robot head.
- **Hermes draws when stuck** brings a card after 3 failed tool calls out of the last 5 in one turn,
  not only after 3 in a row. The count stays within one turn. One card per turn at most: the
  setting `autodraw_per_turn` is gone.
- Hermes draws only cards written for it (tagged `auto`), from decks whose Hermes switch is on: the
  Agent deck by default. The setting `autodraw_decks` is gone; on the first read after the update,
  a stored list sets the deck switches once. When the error says a server could not be reached, a
  card about reframing the problem comes first.
- What Hermes reads is shorter: the card's back, one sentence and a draw id, about 300 characters.
  The call still counts as failed.
- The Hermes tab: the switch with one sentence and an example card, **Failed calls before a card**
  (2 to 6), a switch for each deck with cards written for Hermes, and **What Hermes drew lately**
  with where the turn ran (Desktop chat, Kanban task, Cron job, CLI, Delegated task) and what the
  next call did, as a fact. Draws in runs nobody watched show up there too.
- The page saves settings through a new route that takes only the plugin's five settings, one at a
  time, and refuses to save in unattended runs.
- On a turn where Hermes drew a card, one line follows the reply: the card itself in Desktop, a plain
  line on other surfaces.
- The status bar chip carries the card of the day again, as one line. Its popover holds the card,
  **Pass it to Hermes**, **Another** and **Open Unblockbrücke**. When Hermes draws in the chat in
  focus, the chip shows that card's line and a dot until you click it, the next turn starts or
  another chat gets focus; the popover then asks **Helped** or **Not this time**. The chip asks about
  Hermes' draws only while the feature is on. With the card of the day off, it reads Draw.
- Decks: your own decks save at once, with **Undo**, without a preview and without a file name
  field (it is made from the name). Tags are optional in your own decks; community deck files still
  need 1 to 4 per card. A shipped deck has one **Make my own copy**. Row actions show on hover, there
  is one **Export**, and each deck has one **Draw** switch (the second switch moved to the Hermes
  tab).
- The settings page is a pointer: **Open Unblockbrücke**, the **Sidebar** block and the update line.
  The deck switches and **Reset learning** moved onto the page. The setting texts are shorter.
- The command palette has **Draw a card**, **Draw from <deck>** and **Open Unblockbrücke**; **Open
  decks** is gone.
- Desktop's own tabs, switches, popover and segmented control where Desktop provides them.
- The bundled skill is shorter, with the same rules.
- 28 new cards: Shaders, Writing and Design 8 each, Human 4. They are creative moves on work that
  already runs as well as ways out of a block. Six decks now hold 108 cards.
- The sidebar row and the settings page use the `copy` icon, the closest built-in icon to the
  status bar's two cards.
- Your own copy of a shipped deck replaces that deck on the page, so it does not get the new cards.
  To get them, **Export** your copy, **Delete deck**, and press **Make my own copy** on the shipped
  deck again.

## 0.1.4

- The sidebar row has a place among the Studio Luftbrücke rows: position 53, below Kanban (50).
  The plugin's settings page (Decks and learning) has a **Sidebar** block: **Show in the sidebar**
  and **Position** (1 to 99, lower sits higher). Both are kept per Desktop, so a second computer
  starts with the defaults.
- The setting `show_in_sidebar` leaves Agent settings. The updated Desktop takes its value over
  once, from its first settings read, and keeps the choice from then on. A user who had switched
  the row off sees it until that first read after the update. The plugin still answers the old
  value, read-only, so the takeover works in either update order.
- New palette row **Open Unblockbrücke** opens the page, beside **Open decks**. With the row
  hidden, the Sidebar block names it.

## 0.1.3

- The plugin is spelled **Unblockbrücke**, like its Studio Luftbrücke siblings, and the name
  "UnblockCards" is gone. The sidebar row, the page title, the card back, the status bar and the
  Settings ▸ Plugins entry all read Unblockbrücke. The settings page that entry opens is headed
  "Decks and learning"; the plugin's settings form sits beneath it in Agent settings. Slug, tools,
  decks and the data folder do not change, so nothing moves on update.
- **Draw** in the status bar replaces the card-of-the-day chip: an icon and the word Draw. It opens
  the popover with deck chips, draws, and **Use in chat** puts the card into the chat's draft
  without sending. The popover starts on the deck you last drew from in this profile, else a deck
  named like the profile (`coding` gives Coding), else Human unblock. The 0.1.2 deck choice is not
  carried over, so every profile starts with its own match.
- The card of the day is one line in the popover before you draw; click it to see the card.
- When Hermes draws a card in the chat you are in, a dot appears on the Draw icon until you open
  the popover. The 30-second "Hermes drew" label is gone.
- The human face is white with black text, the agent face black with white text, on the page, in
  the popover and in chat.
- New setting `show_in_statusbar` (on). Desktop's right-click menu on the status bar lists the
  button as Unblockbrücke too. With the button hidden, the shortcut and the palette draw onto the
  page.

## 0.1.2

- Names and copy, no behaviour change. The plugin is **UnblockBrücke** (Settings entry, toasts,
  README); the sidebar row and page are **UnblockCards**; the tagline is "Cards to unblock yourself
  or your agent". The auto-draw setting reads "Hermes draws when stuck". Manifest and setting texts
  are shorter, the `unblockbruecke_card` description starts with what it is for (draw a card when
  you or the user are stuck), and the skill is tighter with the same instructions.

## 0.1.1

- Lean README with screenshots, a banner (`docs/`), and a "How pull requests land" section in
  `CONTRIBUTING.md`. No code change: the version moves so that this tree does not share the label
  0.1.0 with the earlier release.

## 0.1.0

- First release: the card table, auto-draw, six decks, your own decks, the journal, card of the day.
