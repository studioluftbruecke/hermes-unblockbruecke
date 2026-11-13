"""The chip in the status bar and its popover (PLAN-v0.2 M3, sketch A), the pressed deck chip the
shortcut and Another draw from, and "Pass it to Hermes", driven in node through the stand-ins in
test_ui_review.py (same renderer, same `ctx.rest` fake, same deck data).

Skipped without node and desktop/build/node_modules, like test_ui_review.py.
"""
import pytest

from test_ui_review import MODULES, NODE, run_js

pytestmark = pytest.mark.skipif(not NODE or not (MODULES / "esbuild").is_dir(),
                                reason="node and desktop/build/node_modules (npm ci) are needed to run desktop/src")

POPOVER = """
import { Chip } from '@src/chip.js'
import { setCtx } from '@src/core.js'
import { $popCard, $popOpen } from '@src/state.js'
import { jsx } from 'react/jsx-runtime'
import { fakeCtx, setAnswer, rests, mount, all, text, button, host, queryClient } from './helpers.js'
import { DECKS, CARD, K } from './data.js'
const ctx = fakeCtx()
setCtx(ctx)
const drafts = []
host.composer = { getDraft: async () => '', setDraft: async (a, t) => { drafts.push(t); return true }, submit: () => { drafts.push('SUBMIT') } }
setAnswer((m, p, b) => (m === 'POST' && p === '/draw' ? { ok: true, schema: 1, card: { ...CARD, deck: b.deck || 'any' }, draw_id: 'd-' + rests.length } : { ok: true, schema: 1 }))
queryClient.setQueryData(K('decks'), DECKS)
queryClient.setQueryData(K('today'), { ok: true, schema: 1, enabled: true, date: '2026-11-11', card: CARD })
const pop = tree => all(tree, n => n.props['data-ubk'] === 'popover')[0]
const labels = tree => all(pop(tree), n => n.type === 'button').map(text)
"""

LINE = "Read the error as a stranger."


def test_the_chip_carries_the_card_of_the_day_and_names_the_product_for_screen_readers(tmp_path):
    """0.2: the chip is the icon and the card of the day's line; without a card of the day it says Draw.
    The accessible name carries the product name; nothing names the shortcut."""
    out = run_js(tmp_path, POPOVER + """
        const look = () => { const chip = all(mount(jsx(Chip, {})).tree, n => n.props['data-ubk'] === 'chip')[0]
          return { text: text(chip), title: chip.props.title, aria: chip.props['aria-label'], svg: all(chip, n => n.type === 'svg').length } }
        const day = look()
        queryClient.setQueryData(K('today'), { ok: true, schema: 1, enabled: false, date: '2026-11-11', card: null })
        console.log(JSON.stringify({ day, off: look() }))
    """)
    assert out["day"] == {"text": LINE, "title": f"Card of the day: {LINE}", "aria": f"Unblockbrücke, card of the day: {LINE}", "svg": 1}, out
    assert out["off"] == {"text": "Draw", "title": "Draw a card", "aria": "Unblockbrücke, draw a card", "svg": 1}, out


def test_popover_card_of_the_day_another_and_pass_it_to_hermes(tmp_path):
    """Sketch A: the popover holds the card, "Pass it to Hermes", "Another" and the page link (three
    controls). Another draws from the pressed chip of this profile and shows that card; "Pass it to
    Hermes" drafts both faces and the directive line, never sends, and closes the popover."""
    out = run_js(tmp_path, POPOVER + """
        host.state.focusedSessionProfile.set('coding')
        ctx.storage.set('pressed:coding', 'writing')
        $popOpen.set(true)
        const view = mount(jsx(Chip, {}))
        const res = { day: { state: pop(view.tree).props['data-state'], labels: labels(view.tree), cards: all(pop(view.tree), n => n.props['data-card']).map(n => [n.props['data-card'], n.props['data-face'], n.props.role || null]) } }
        button(pop(view.tree), /^Another$/).props.onClick()
        await view.settle()
        const t = view.render()
        res.after = { state: pop(t).props['data-state'], labels: labels(t), sent: rests.filter(([m, p]) => p === '/draw').map(r => r[2].deck) }
        button(pop(t), /^Pass it to Hermes$/).props.onClick()
        await view.settle()
        res.drafts = drafts
        res.open = $popOpen.get()
        console.log(JSON.stringify(res))
    """)
    assert out["day"] == {"state": "day", "labels": ["Pass it to Hermes", "Another", "Open Unblockbrücke"], "cards": [["coding/co-03", "front", None]]}, out["day"]
    assert out["after"] == {"state": "drawn", "labels": ["Pass it to Hermes", "Another", "Open Unblockbrücke"], "sent": ["writing"]}, out["after"]
    assert out["drafts"] == ['::card{deck="coding" id="co-03"}\nI drew "Read the error as a stranger." (Coding).\nFor Hermes: Quote the exact error line, then list two readings.'], out["drafts"]
    assert out["open"] is False


def test_with_card_of_the_day_off_the_popover_offers_draw(tmp_path):
    """card_of_day off and nothing drawn: the popover shows the card back, Draw and the page link."""
    out = run_js(tmp_path, POPOVER + """
        queryClient.setQueryData(K('today'), { ok: true, schema: 1, enabled: false, date: '2026-11-11', card: null })
        $popOpen.set(true)
        const view = mount(jsx(Chip, {}))
        const res = { state: pop(view.tree).props['data-state'], labels: labels(view.tree) }
        button(pop(view.tree), /^Draw$/).props.onClick()
        await view.settle()
        res.after = pop(view.render()).props['data-state']
        console.log(JSON.stringify(res))
    """)
    assert out == {"state": "empty", "labels": ["Draw", "Open Unblockbrücke"], "after": "drawn"}, out


def test_the_pressed_chip_starts_on_human_and_falls_back_to_all(tmp_path):
    """His rule: Human on a first run; exactly one chip pressed. A deck list without Human starts on All;
    0.1's `deck` and `deck:<profile>` keys are not carried over."""
    out = run_js(tmp_path, """
        import { ALL, chipList, pressedChip } from '@src/state.js'
        import { DECKS } from './data.js'
        const human = { deck: 'human-unblock', name: 'Human', source: 'shipped', cards: 24, switch: { draw: true, auto: false } }
        const own = { deck: 'human-unblock-own', name: 'Human', source: 'own', copy_of: 'human-unblock', cards: 25, switch: { draw: true, auto: false } }
        const withHuman = [...DECKS.decks, human]
        const shadowed = [...DECKS.decks, { ...human, shadowed_by: 'human-unblock-own' }, own]
        console.log(JSON.stringify({
          first: pressedChip(withHuman, ''), stored: pressedChip(withHuman, 'coding'), all: pressedChip(withHuman, ALL), gone: pressedChip(withHuman, 'nope'),
          noHuman: pressedChip(DECKS.decks, ''), ownCopy: pressedChip(shadowed, ''),
          order: chipList(withHuman).map(c => c.name), ownOrder: chipList(shadowed).map(c => c.key),
        }))
    """)
    assert out["first"] == "human-unblock" and out["stored"] == "coding" and out["all"] == "all" and out["gone"] == "human-unblock", out
    assert out["noHuman"] == "all" and out["ownCopy"] == "human-unblock-own", out
    assert out["order"] == ["Human", "Coding", "Writing", "Agent unblock", "Mine", "Night shift", "All"], out
    assert out["ownOrder"][0] == "human-unblock-own", out


def test_a_popover_draw_with_the_chip_hidden_opens_the_page(tmp_path):
    """A draw meant for the popover (palette, shortcut, away from the page) while the chip is not
    mounted puts the card on the page's table and navigates there; no popover opens."""
    out = run_js(tmp_path, POPOVER + """
        import { $table, drawCard, setChipMounted } from '@src/state.js'
        globalThis.window.location.hash = '#/chat'
        setChipMounted(false)
        await drawCard({ deck: 'coding', where: 'chip' })
        const hidden = { nav: globalThis.__calls.filter(c => c[0] === 'navigate'), open: $popOpen.get(), table: $table.get() && $table.get().card.id }
        setChipMounted(true)
        await drawCard({ deck: 'coding' })
        const shown = { nav: globalThis.__calls.filter(c => c[0] === 'navigate').length, open: $popOpen.get(), pop: $popCard.get() && $popCard.get().card.id }
        console.log(JSON.stringify({ hidden, shown }))
    """)
    assert out["hidden"] == {"nav": [["navigate", "/unblockbruecke"]], "open": False, "table": "co-03"}, out
    assert out["shown"] == {"nav": 1, "open": True, "pop": "co-03"}, out


def test_a_chip_that_throws_renders_nothing_inside_its_boundary(tmp_path):
    """The status-bar item has no Desktop ContribBoundary around it (data path), so the chip carries
    its own: a throwing child leaves an empty slot instead of taking the status bar down."""
    out = run_js(tmp_path, """
        import { Boundary } from '@src/chip.js'
        const b = new Boundary({ children: 'x' })
        const before = b.render()
        b.state = Boundary.getDerivedStateFromError(new Error('boom'))
        console.log(JSON.stringify({ before, after: b.render() }))
    """)
    assert out == {"before": "x", "after": None}, out
