# Propose a deck

Unblockbrücke ships decks written for it. You can propose your own deck for everyone: open a
pull request to this repository that adds one file, `data/decks/community/<your-deck>.yaml`. Every
deck is read and reviewed before it ships, because its cards end up in people's chats and, if they
switch it on, in their agent's context.

## Before you open the pull request

1. **Write the deck in the plugin.** On the Unblockbrücke page, open the **Decks** tab, press **New
   deck** and add your cards, or ask Hermes ("make me a deck for mixing music with five cards").
   Press **Export** when you are happy with it. A deck file looks like this:

   ```yaml
   schema: 1
   deck: mixing
   name: Mixing
   by: Your Name
   license: CC-BY-4.0        # or CC0-1.0
   version: 1
   faces: [human, agent]
   mark: sphere              # see "Marks" below
   description: For a mix that will not move
   glossary:
     space: Makes room in the mix instead of adding to it.
   cards:
     - id: mx-01
       human: Mute the part you love most.
       agent: Ask which track the user likes best, suggest muting it for one listen, then ask what the song needs.
       tags: [space]
   ```

2. **Give every card 1 to 4 tags.** In the plugin, tags are optional in your own decks, so an
   exported deck may have cards without any. A community deck needs 1 to 4 tags on every card.
   Each tag is a short lowercase word with one line in `glossary`, except the two built-in tags:
   `human` (the card asks a person something) and `auto` (written for Hermes when its tool calls
   keep failing; Hermes draws only these when stuck).

3. **Check it.** From the plugin folder run:

   ```bash
   python3 scripts/check_deck.py data/decks/community/mixing.yaml
   ```

   It needs `ruamel.yaml` (Hermes ships it). It prints `ok`, or each rule a card breaks.

4. **Read the rules the check cannot judge.**
   - Every word is yours. No lines from another deck, book or app, and no close paraphrases. The
     original Oblique Strategies are not included; the maintainer checks every proposed deck against
     them, because `check_deck.py` cannot.
   - A card names an operation, not an attitude: the agent face is one concrete, safe instruction.
   - No card tells anyone to delete, install, push, deploy, call the network or change a model.
   - Only cards tagged `human` ask a person something.
   - A card tagged `auto` reaches Hermes right after several failed tool calls: its agent face is a
     next move that works without a person.
   - Five good cards beat thirty vague ones.

## Names

- `name` is what people read on the deck chip: one line of 1 to 40 characters, plain text (no HTML,
  Markdown links, backticks, web addresses, shell commands or @mentions). Keep it short, like the shipped decks: Human,
  Agent, Coding, Writing, Design, Shaders.
- `deck` is the file name without `.yaml`: 2 to 40 characters of `a` to `z`, `0` to `9` and `-`,
  starting with a letter or a digit. It cannot be the file name of a shipped deck (`human-unblock`,
  `agent-unblock`, `coding`, `writing`, `design`, `shaders`).
- In the plugin, a new deck's file name is made from its name, and a name a shipped deck already has
  is refused: open that deck and press **Make my own copy** instead.
- Card ids share one prefix of 2 to 4 letters, then a dash and two digits (`mx-01`). The human face
  has at most 90 characters, the agent face at most 220, each on one line, under the same plain-text
  rules as `name`.

## Marks

`mark` picks the glyph on the deck's chip and in the corner of its cards. One of the six glyphs the
shipped decks use:

| `mark` | Glyph | Shipped deck |
| --- | --- | --- |
| `person` | a person | Human |
| `code` | two chevrons | Coding |
| `pencil` | a pencil | Writing |
| `shapes` | a triangle, a square and a circle | Design |
| `sphere` | a shaded sphere | Shaders |
| `robot` | a robot head | Agent |

The six shapes of 0.1 (`square`, `circle`, `triangle`, `diamond`, `half`, `ring`) are still valid
and are drawn as flat shapes. Pick the glyph closest to your deck's subject.

## Licence

Pick `CC-BY-4.0` (people credit you when they share your deck) or `CC0-1.0` (no conditions). The
pull request template asks you to confirm that the text is your own work.

## What happens next

The maintainer at Studio Luftbrücke reads every deck and may ask for changes, merge it, or decline it
with a reason. A merged deck ships with the next release of the plugin, with your name in its `by` line.

## How pull requests land

Development happens in a private workbench. A pull request accepted here is ported into it by hand,
with `Co-authored-by:` credit, and released in the next version. The GitHub pull request is then
closed with a link to that release. Closed is not rejected: your change is in the release it links.
For a bug or an idea that is not a deck, open a GitHub issue first.
