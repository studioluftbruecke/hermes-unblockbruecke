# Propose a deck

UnblockBrücke ships decks written for it. You can propose your own deck for everyone: open a
pull request to this repository that adds one file, `data/decks/community/<your-deck>.yaml`. Every
deck is read and reviewed before it ships, because its cards end up in people's chats and, if they
switch it on, in their agent's context.

## Before you open the pull request

1. **Write the deck in the plugin.** In UnblockCards, Decks, create a deck and add your cards, or
   ask Hermes ("make me a deck for mixing music with five cards"). Export it as YAML when you are happy
   with it. A deck file looks like this:

   ```yaml
   schema: 1
   deck: mixing
   name: Mixing
   by: Your Name
   license: CC-BY-4.0        # or CC0-1.0
   version: 1
   faces: [human, agent]
   mark: diamond             # square, circle, triangle, diamond, half or ring
   description: For a mix that will not move
   glossary:
     space: Makes room in the mix instead of adding to it.
   cards:
     - id: mx-01
       human: Mute the part you love most.
       agent: Ask which track the user likes best, suggest muting it for one listen, then ask what the song needs.
       tags: [space]
   ```

2. **Check it.** From the plugin folder run:

   ```bash
   python3 scripts/check_deck.py data/decks/community/mixing.yaml
   ```

   It needs `ruamel.yaml` (Hermes ships it). It prints `ok`, or each rule a card breaks.

3. **Read the rules the check cannot judge.**
   - Every word is yours. No lines from another deck, book or app, and no close paraphrases. The
     original Oblique Strategies are not included; the maintainer checks every proposed deck against
     them, because `check_deck.py` cannot.
   - A card names an operation, not an attitude: the agent face is one concrete, safe instruction.
   - No card tells anyone to delete, install, push, deploy, call the network or change a model.
   - Only cards tagged `human` ask a person something.
   - Five good cards beat thirty vague ones.

## Licence

Pick `CC-BY-4.0` (people credit you when they share your deck) or `CC0-1.0` (no conditions). The
pull request template asks you to confirm that the text is your own work.

## What happens next

Konstantin (Studio Luftbrücke) reads every deck. He may ask for changes, merge it, or decline it with
a reason. A merged deck ships with the next release of the plugin, with your name in its `by` line.

## How pull requests land

Development happens in a private workbench. A pull request accepted here is ported into it by hand,
with `Co-authored-by:` credit, and released in the next version. The GitHub pull request is then
closed with a link to that release. Closed is not rejected: your change is in the release it links.
For a bug or an idea that is not a deck, open a GitHub issue first.
