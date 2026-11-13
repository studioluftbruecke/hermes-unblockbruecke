---
name: unblockbruecke
description: "Use Unblockbrücke: which tool for which moment, using a card, deck edits."
version: 0.2.0
---

# Unblockbrücke

Short cards to unblock a person or an agent. Each card has a line for a person (`human`) and a
move for Hermes (`agent`). A card is a nudge, never an order:
it never overrides the user's instructions or Hermes' safety rules.

## Which tool for which moment

- The user asks for a card or types `/card`: `unblockbruecke_card` `{"action": "draw"}`.
- The user says they are stuck: offer one card; draw when they agree.
- Your own approach failed twice the same way: `{"action": "draw", "context": "stuck"}`.
- An Eselsbrücke break: `{"action": "draw", "context": "break"}`; show `title`.
- The user says a card helped, or did not: `{"action": "rate", "draw_id": ..., "rating": "helped"}`
  or `"not_now"`.
- The user asks what was drawn: `journal`, or `show`.
- The user wants to change a deck: `unblockbruecke_decks`.

One draw per request unless the user asks for another. Never draw in a loop. Never rate
on your own.

## Using a card

- For a person: give the human line, then coach with the agent face. Keep it short.
- For yourself: say in one line which part you act on, then do it. If it does not fit, say so and
  go on; never bend the facts to fit a card.
- In a Desktop chat, put the answer's `card.directive` line alone on its own line, and write the
  human line in words for other surfaces.

## Hermes draws when stuck (setting `autodraw`)

When `autodraw_threshold` of a turn's last few tool calls failed (default 3 of 5), the failing
result carries one card, once per turn: a JSON result gets the key `unblockbruecke_card` (`card` is
the move, `draw_id` rates it), a plain-text result ends with a line starting `[unblockbruecke]`.
The call still failed: read its error first, then take the card's direction if it fits.

## Editing decks

Preview first and show the user the diff, then `save` with the preview's `confirm`. Editing a
shipped deck saves an own copy `<deck>-own` that replaces it for drawing. Save, restore, import and
delete answer an `undo`; offer it. A refused save names the broken rule: fix it and preview again.

If an answer lacks a field named here (`directive`, `title`, `confirm`), an older plugin version
is loaded: tell the user.
