"""The Draw button and its popover (PLAN-v0.1.3 M2: A17 to A19, A22, P1 to P3), driven in node through
the stand-ins in test_ui_review.py (same renderer, same `ctx.rest` fake, same deck data).

Skipped without node and desktop/build/node_modules, like test_ui_review.py.
"""
import pytest

from test_ui_review import MODULES, NODE, run_js

pytestmark = pytest.mark.skipif(not NODE or not (MODULES / "esbuild").is_dir(),
                                reason="node and desktop/build/node_modules (npm ci) are needed to run desktop/src")

POPOVER = """
import { Chip } from '@src/chip.js'
import { setCtx } from '@src/core.js'
import { $popCard, $popDeck, $popOpen } from '@src/state.js'
import { jsx } from 'react/jsx-runtime'
import { fakeCtx, setAnswer, rests, mount, all, text, button, host, queryClient } from './helpers.js'
import { DECKS, CARD, K } from './data.js'
const ctx = fakeCtx()
setCtx(ctx)
setAnswer((m, p, b) => (m === 'POST' && p === '/draw' ? { ok: true, schema: 1, card: { ...CARD, deck: b.deck || 'writing' }, draw_id: 'd-' + rests.length } : { ok: true, schema: 1 }))
queryClient.setQueryData(K('decks'), DECKS)
queryClient.setQueryData(K('today'), { ok: true, schema: 1, enabled: true, date: '2026-11-11', card: CARD })
const pop = tree => all(tree, n => n.props['data-ubk'] === 'popover')[0]
const labels = tree => all(pop(tree), n => n.type === 'button' && !n.props['data-deck'] && n.props['data-ubk'] !== 'today').map(text)
const chips = tree => all(pop(tree), n => n.props['data-deck']).map(n => [n.props['data-deck'], !!n.props['aria-pressed']])
"""


def test_the_button_says_draw_and_names_the_product_for_screen_readers(tmp_path):
    """A17: the visible text is exactly "Draw" next to an icon; the tooltip says "Draw a card"; the
    accessible name carries the product name. Neither names the shortcut (RV5)."""
    out = run_js(tmp_path, POPOVER + """
        const chip = all(mount(jsx(Chip, {})).tree, n => n.props['data-ubk'] === 'chip')[0]
        console.log(JSON.stringify({ text: text(chip), title: chip.props.title, aria: chip.props['aria-label'], svg: all(chip, n => n.type === 'svg').length }))
    """)
    assert out == {"text": "Draw", "title": "Draw a card", "aria": "Unblockbrücke: draw a card", "svg": 1}, out


def test_popover_before_a_draw_then_after_it(tmp_path):
    """A18, P1, P2: before a draw the popover shows the drawable decks as chips with the default
    selected, the Today line and Draw. Draw sends that deck, saves it as this profile's last deck and
    turns the popover into the card with Use in chat, Draw another and the page link; Ask Hermes and
    Show agent face stay on the page only. A chip after a draw draws from that deck at once."""
    out = run_js(tmp_path, POPOVER + """
        host.state.focusedSessionProfile.set('coding')
        $popOpen.set(true)
        const view = mount(jsx(Chip, {}))
        const res = { before: { state: pop(view.tree).props['data-state'], chips: chips(view.tree), labels: labels(view.tree) } }
        button(pop(view.tree), /^Draw$/).props.onClick()
        await view.settle()
        const t = view.render()
        res.after = { state: pop(t).props['data-state'], labels: labels(t), cards: all(pop(t), n => n.props['data-card']).length, hint: text(all(pop(t), n => n.props.className === 'hint')) }
        res.sent = rests.filter(([m, p]) => p === '/draw').map(r => r[2].deck)
        res.saved = ctx.storage.get('deck:coding', null)
        all(pop(t), n => n.props['data-deck'] === 'writing')[0].props.onClick()
        await view.settle()
        res.chipDraw = { sent: rests.filter(([m, p]) => p === '/draw').map(r => r[2].deck), saved: ctx.storage.get('deck:coding', null), picked: $popDeck.get() }
        button(pop(view.render()), /^Draw another$/).props.onClick()
        await view.settle()
        res.another = rests.filter(([m, p]) => p === '/draw').map(r => r[2].deck)
        console.log(JSON.stringify(res))
    """)
    assert out["before"]["state"] == "before"
    assert out["before"]["chips"] == [["agent-unblock", False], ["coding", True], ["writing", False], ["night-shift", False], ["mine", False]], out
    assert out["before"]["labels"] == ["Draw", "Open Unblockbrücke"], out
    assert out["after"]["state"] == "after" and out["after"]["cards"] == 1, out
    assert out["after"]["labels"] == ["Use in chat", "Draw another", "Open Unblockbrücke"], out
    assert out["after"]["hint"] == "Click to turn"
    assert out["sent"] == ["coding"] and out["saved"] == "coding", out
    assert out["chipDraw"] == {"sent": ["coding", "writing"], "saved": "writing", "picked": "writing"}, out
    assert out["another"] == ["coding", "writing", "writing"], out


def test_today_line_follows_the_card_of_the_day_setting(tmp_path):
    """A19: with card_of_day off (GET /today enabled false) the popover has no Today line."""
    out = run_js(tmp_path, POPOVER + """
        $popOpen.set(true)
        const on = all(mount(jsx(Chip, {})).tree, n => n.props['data-ubk'] === 'today').map(text)
        queryClient.setQueryData(K('today'), { ok: true, schema: 1, enabled: false, date: '2026-11-11', card: null })
        const off = all(mount(jsx(Chip, {})).tree, n => n.props['data-ubk'] === 'today').map(text)
        console.log(JSON.stringify({ on, off }))
    """)
    assert out == {"on": ["Today: Read the error as a stranger."], "off": []}, out


def test_default_deck_order(tmp_path):
    """P1: last deck while drawable, then the profile match (exact, plural, singular), then Human
    unblock, else any deck. A host without focusedSessionProfile still answers (P-PROF)."""
    out = run_js(tmp_path, """
        import { currentProfile, defaultDeck } from '@src/state.js'
        import { host } from './helpers.js'
        const on = slug => ({ deck: slug, name: slug, switch: { draw: true, auto: false } })
        const off = slug => ({ deck: slug, name: slug, switch: { draw: false, auto: false } })
        const decks = [on('human-unblock'), on('coding'), on('shaders'), on('design'), on('writing'), off('night-shift')]
        const res = {
          lastWins: defaultDeck({ decks, profile: 'coding', last: 'writing' }),
          lastOff: defaultDeck({ decks, profile: 'coding', last: 'night-shift' }),
          lastGone: defaultDeck({ decks, profile: 'coding', last: 'no-such' }),
          coding: defaultDeck({ decks, profile: 'coding', last: '' }),
          shader: defaultDeck({ decks, profile: 'shader', last: '' }),
          designs: defaultDeck({ decks, profile: 'designs', last: '' }),
          nomatch: defaultDeck({ decks, profile: 'default', last: '' }),
          noHuman: defaultDeck({ decks: decks.filter(d => d.deck !== 'human-unblock'), profile: 'default', last: '' }) ?? null,
          none: defaultDeck({ decks: [], profile: 'coding', last: 'coding' }) ?? null,
        }
        host.state.focusedSessionProfile.set('shaders')
        res.focused = currentProfile()
        host.state.focusedSessionProfile.set(null)
        res.unfocused = currentProfile()
        delete host.state.focusedSessionProfile
        res.oldHost = currentProfile()
        host.state.profile.set(null)
        res.bare = currentProfile()
        console.log(JSON.stringify(res))
    """)
    assert out == {"lastWins": "writing", "lastOff": "coding", "lastGone": "coding", "coding": "coding", "shader": "shaders",
                   "designs": "design", "nomatch": "human-unblock", "noHuman": None, "none": None,
                   "focused": "shaders", "unfocused": "test", "oldHost": "test", "bare": "default"}, out


def test_old_deck_key_is_not_carried_over(tmp_path):
    """A22: a 0.1.2 value in `deck` and an empty `deck:coding` leave a coding chat on Coding."""
    out = run_js(tmp_path, POPOVER + """
        ctx.storage.set('deck', 'writing')
        host.state.focusedSessionProfile.set('coding')
        $popOpen.set(true)
        console.log(JSON.stringify({ chips: chips(mount(jsx(Chip, {})).tree).filter(c => c[1]).map(c => c[0]) }))
    """)
    assert out == {"chips": ["coding"]}, out


def test_a_popover_draw_with_the_button_hidden_opens_the_page(tmp_path):
    """A draw meant for the popover (palette, shortcut, away from the page) while the Draw button is
    not mounted puts the card on the page's table and navigates there; no popover opens."""
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
