# Changelog

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
