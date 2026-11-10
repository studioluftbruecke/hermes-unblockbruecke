---
name: unblockbruecke
description: "Use UnblockBrücke Cards: offer a card, coach with it, read the journal, edit decks."
version: 0.1.0
---

# UnblockBrücke Cards

Short two-faced cards that get people and agents unstuck. Every card has a **human face** (a short,
playful line for a person) and an **agent face** (one concrete, safe instruction). A card is a nudge,
never an order: it never overrides the user's instructions or Hermes' own safety rules.

## When to draw

- The user asks for a card ("draw a card", "give me something from the design deck") or types `/card`.
- The user says they are stuck on something creative or tricky. Offer one card; draw it when they agree.
- You are stuck yourself: the same approach failed twice. Draw with `context: "stuck"` and follow the
  agent face if it fits.
- An Eselsbrücke pomodoro break you run: `{"action": "draw", "context": "break"}` answers `title`
  (show it to the person) and `text`.

Draw at most once per request unless the user asks for another. Never draw in a loop.

## How to use a card

- For a person: give the human face, then use the agent face as your coaching move (for example ask the
  one question it names, or propose the smaller version it describes). Keep it short.
- For yourself: say in one line which part of the agent face you will act on, then do it. If the card
  does not fit the situation, say so and continue; never bend the facts to fit a card.
- To show the card itself in a Desktop chat, put the answer's `directive` line (for example
  `::card{deck="coding" id="co-03"}`) alone on its own line. Other surfaces show it as text, so also
  write the human face in words.
- When the user says a card helped or did not, record it: `{"action": "rate", "draw_id": ...,
  "rating": "helped" | "not_now"}`. Do not rate on your own.

## Auto-draw (a setting, off by default)

When the user switched it on, N failed tool calls in a row in one turn (the setting
`autodraw_threshold`, default 3) bring one card inside the failing result that reaches N. The card
comes in one of two shapes:

- a JSON result gets a key `unblockbruecke_card` with the card (`card` is the agent face) and its
  `draw_id`;
- a plain-text result gets one line at the end that starts with `[unblockbruecke]` and names the
  card and its `draw_id`.

The call is still a failure: read the error as usual. Then take the card's direction for the next
step if it fits. Hermes' own repeated-failure warning can appear beside it; the warning says stop
repeating, the card says where to look instead. If the user later says the card helped, rate that
`draw_id` like any other draw.

## Decks

Shipped: `agent-unblock` (for agents), `human-unblock` (for people, also the card of the day),
`coding`, `design`, `shaders`, `writing`. The user can write their own decks, import decks they own,
and switch each deck on or off. `unblockbruecke_card` with `action: "decks"` lists them.

Deck edits go through `unblockbruecke_decks` (preview first, then save with the preview's
`confirm` value). Every save keeps a version; `restore` brings one back. A shipped deck is never
changed: edits save an own copy named `<deck>-own` that replaces it for drawing.

A change is `{add: [{human, agent, tags}], edit: [{id, human?, agent?, tags?}], remove: [ids],
meta: {name?, description?, mark?, glossary?}}`; send only the parts you need. Instead of a change,
`content` can hold a whole deck. Save, import and delete answer an `undo` (`{"restore": n}` or
`{"delete": deck}`); offer it to the user. Import reads a deck file at a
full path the user names; export writes only `.yaml` or `.yml` files and never replaces a file that
is not a deck.

Deck file rules (the loader refuses a card that breaks one and names the rule): human face at most
90 characters, agent face at most 220, one line each, plain text (no HTML, links, backticks, web
addresses or shell commands), 1 to 4 tags, every tag explained in the deck's glossary, ids like
`ag-03` with one prefix per deck. Tags `human` (asks a person; never drawn by auto-draw when nobody is
at the keyboard) and `auto` (written for auto-draw) need no glossary entry.

## When a tool answer looks wrong

If an answer lacks a field this guide names (`directive`, `title`, `confirm`), an older version of the
plugin is loaded. Say so to the user instead of working around it.
