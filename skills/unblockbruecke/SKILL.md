---
name: unblockbruecke
description: "Use UnblockBrücke: offer a card, coach with it, read the journal, edit decks."
version: 0.1.2
---

# UnblockBrücke

Cards to unblock yourself or your agent. Each card has a **human face** (a short line for a person)
and an **agent face** (one concrete, safe instruction). A card is a nudge, never an order: it never
overrides the user's instructions or Hermes' safety rules.

## When to draw

- The user asks for a card ("draw a card", "something from the design deck") or types `/card`.
- The user says they are stuck. Offer one card; draw it when they agree.
- You are stuck: the same approach failed twice. Draw with `context: "stuck"`; follow the agent face
  if it fits.
- An Eselsbrücke pomodoro break: `{"action": "draw", "context": "break"}` answers `title` (show it to
  the person) and `text`.

At most one draw per request unless the user asks for another. Never draw in a loop.

## Using a card

- For a person: give the human face, then use the agent face as your coaching move (ask the question
  it names, propose the smaller version it describes). Keep it short.
- For yourself: say in one line which part you act on, then do it. If it does not fit, say so and
  continue; never bend the facts to fit a card.
- In a Desktop chat, put the answer's `directive` line (e.g. `::card{deck="coding" id="co-03"}`)
  alone on its own line; also write the human face in words for other surfaces.
- When the user says a card helped or not: `{"action": "rate", "draw_id": ..., "rating": "helped" |
  "not_now"}`. Never rate on your own.

## Hermes draws when stuck (setting `autodraw`, off by default)

When on, N failed tool calls in a row in one turn (`autodraw_threshold`, default 3) bring one card
in the failing result that reaches N: a JSON result gets a key `unblockbruecke_card` (`card` is the
agent face) with its `draw_id`; a plain-text result ends with a line starting `[unblockbruecke]`
naming the card and `draw_id`. The call still failed: read the error, then take the card's
direction if it fits. Hermes' repeated-failure warning may appear too: it says stop repeating, the
card says where to look. Rate that `draw_id` if the user says it helped.

## Decks

Shipped: `agent-unblock`, `human-unblock` (also the card of the day), `coding`, `design`, `shaders`,
`writing`. Users write, import and switch their own decks; `unblockbruecke_card` with
`action: "decks"` lists them.

Edit with `unblockbruecke_decks`: preview first, then save with the preview's `confirm`. Every save
keeps a version; `restore` brings one back. Edits to a shipped deck save an own copy `<deck>-own`
that replaces it for drawing. A change is `{add: [{human, agent, tags}], edit: [{id, human?, agent?,
tags?}], remove: [ids], meta: {name?, description?, mark?, glossary?}}`, only the parts you need, or
`content` with a whole deck. Save, import and delete answer an `undo` (`{"restore": n}` or
`{"delete": deck}`); offer it. Import reads a full path the user names; export writes only `.yaml`
or `.yml` and never replaces a file that is not a deck.

Card rules (the loader names the one broken): human face at most 90 characters, agent face at most
220, one line each, plain text (no HTML, links, backticks, web addresses, shell commands), 1 to 4
tags, each in the deck's glossary, ids like `ag-03` with one prefix per deck. Tags `human` (needs a
person; skipped when nobody is at the keyboard) and `auto` (written for auto-draw) need no glossary
entry.

## When an answer looks wrong

If an answer lacks a field named here (`directive`, `title`, `confirm`), an older plugin version is
loaded. Tell the user instead of working around it.
