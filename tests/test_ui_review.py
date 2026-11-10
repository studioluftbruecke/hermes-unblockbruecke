"""The Desktop half's behaviour after the v0.1 review (lane UI): each test drives desktop/src in node.

desktop/src is bundled with the build's own esbuild (desktop/build/node_modules, after `npm ci`) against
three small stand-ins written below: `@hermes/plugin-sdk` (atoms, a host with focused-chat atoms, a
query cache the test fills, ConfirmDialog/Switch/Popover as plain elements), `react` (hooks with state
kept per component path, effects run after each render) and `react/jsx-runtime` (elements as plain
objects). A test renders a component, reads the element tree (text, disabled, dir), and acts on it
through its own handlers (onClick, onChange, onKeyDown), then re-renders. `ctx.rest` answers from
the test's own `answer(method, path, body)`.

This is not React: it proves what the components say and do with the data they get, not layout. The
card's layout at its size limits is the one test that needs a browser (Playwright, see the end of this
file); it is skipped unless UBK_PLAYWRIGHT names the playwright module and UBK_CHROME a Chromium.

Skipped without node and desktop/build/node_modules, like the build tests in test_desktop_build.py.
"""
import json
import os
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

from ub_fakes import ROOT

SRC = ROOT / "desktop" / "src"
MODULES = ROOT / "desktop" / "build" / "node_modules"
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(not NODE or not (MODULES / "esbuild").is_dir(),
                                reason="node and desktop/build/node_modules (npm ci) are needed to run desktop/src")

SDK = r"""
const subs = new Set()
export function atom(value) {
  const a = { get: () => value, set: v => { value = v; subs.forEach(f => f()) }, subscribe: f => { subs.add(f); return () => subs.delete(f) } }
  return a
}
export const useValue = a => (a && a.get ? a.get() : null)
export const host = {
  state: { profile: atom('test'), focusedStoredSessionId: atom(null), focusedSessionId: atom(null) },
  navigate: path => globalThis.__calls.push(['navigate', path]),
  notify: p => globalThis.__toasts.push(p.message),
  composer: { setDraft: async () => true, getDraft: async () => '' },
  newChat: () => {},
}
const key = k => JSON.stringify(k)
export const queryClient = {
  data: new Map(),
  times: new Map(),
  getQueryData: k => queryClient.data.get(key(k)),
  setQueryData: (k, v) => { queryClient.data.set(key(k), v); queryClient.times.set(key(k), Date.now()) },
  invalidateQueries: () => {},
  // React Query's fetchQuery: the cached answer while it is younger than staleTime, else a fresh one.
  async fetchQuery({ queryKey, queryFn, staleTime = 0 }) {
    const k = key(queryKey)
    const v = queryClient.data.get(k)
    if (v !== undefined && !(v instanceof Error) && Date.now() - (queryClient.times.get(k) || 0) < staleTime) return v
    const out = await queryFn()
    queryClient.setQueryData(queryKey, out)
    return out
  },
  // Test only: make a cached answer `ms` older.
  age: (k, ms) => queryClient.times.set(key(k), (queryClient.times.get(key(k)) || Date.now()) - ms),
}
export function useQuery({ queryKey, enabled }) {
  if (enabled === false) return { data: undefined, isLoading: false, error: null }
  const v = queryClient.data.get(key(queryKey))
  if (v instanceof Error) return { data: undefined, isLoading: false, error: v }
  return { data: v, isLoading: v === undefined, error: null }
}
export const ConfirmDialog = 'ConfirmDialog'
export const Switch = 'Switch'
export const Popover = 'Popover'
export const PopoverTrigger = 'PopoverTrigger'
export const PopoverContent = 'PopoverContent'
export const writeClipboardText = async () => {}
export const pluginSettingsHref = id => `/settings/plugins/${id}`
export const ROUTES_AREA = 'routes'
export const STATUSBAR_AREAS = { right: 'statusBar.right' }
export const TRANSCRIPT_DIRECTIVE_AREA = 'transcript.directives'
export const KEYBINDS_AREA = 'keybinds'
export const PALETTE_AREA = 'palette'
export const SIDEBAR_NAV_AREA = 'sidebar.nav'
"""

REACT = r"""
// Hooks keyed by the component's path in the tree; the renderer below sets `cur` per component.
let cur = null
export const __set = c => { cur = c }
const slot = init => {
  const i = cur.i++
  if (!(i in cur.slots)) cur.slots[i] = init()
  return i
}
export function useState(init) {
  const c = cur
  const i = slot(() => (typeof init === 'function' ? init() : init))
  return [c.slots[i], v => { c.slots[i] = typeof v === 'function' ? v(c.slots[i]) : v }]
}
export function useRef(init) {
  const i = slot(() => ({ current: init }))
  return cur.slots[i]
}
export function useEffect(fn, deps) {
  const c = cur
  const i = slot(() => ({ deps: undefined, cleanup: null }))
  const e = c.slots[i]
  const changed = !deps || !e.deps || deps.length !== e.deps.length || deps.some((d, k) => !Object.is(d, e.deps[k]))
  if (changed) c.effects.push(() => { if (e.cleanup) e.cleanup(); e.deps = deps; e.cleanup = fn() || null })
}
export default { useState, useRef, useEffect }
"""

JSX = r"""
export const jsx = (type, props, key) => ({ type, props: props || {}, key })
export const jsxs = jsx
export const Fragment = 'Fragment'
"""

HELPERS = r"""
import { __set } from 'react'
import { host, queryClient } from '@hermes/plugin-sdk'
globalThis.__calls = []
globalThis.__toasts = []
export const rests = []
export let answer = () => ({})
export const setAnswer = f => { answer = f }
export const fakeCtx = () => {
  const reg = []
  const store = new Map()
  return {
    reg, store,
    rest: async (path, opts = {}) => {
      const method = opts.method || 'GET'
      rests.push([method, path, opts.body])
      const out = await answer(method, path, opts.body)
      if (out && out.__status) throw new Error(`${out.__status}: ${typeof out.body === 'string' ? out.body : JSON.stringify(out.body)}`)
      return out
    },
    register: c => { reg.push(c); return () => {} },
    onDispose: () => {},
    storage: { get: (k, d) => (store.has(k) ? store.get(k) : d), set: (k, v) => store.set(k, v) },
  }
}
// ---- the renderer: expand function components, keep hook state per path, run effects ----
export function mount(el) {
  const states = new Map()
  const expand = (node, path) => {
    if (node === null || node === undefined || node === false || node === true) return null
    if (Array.isArray(node)) return node.map((n, i) => expand(n, `${path}.${n && n.key != null ? n.key : i}`))
    if (typeof node !== 'object') return node
    if (typeof node.type === 'function') {
      const p = `${path}/${node.type.name}`
      if (!states.has(p)) states.set(p, { slots: {}, effects: [] })
      const c = states.get(p)
      c.i = 0
      __set(c)
      const out = node.type(node.props)
      __set(null)
      return expand(out, p)
    }
    const kids = node.props.children
    return { type: node.type, props: { ...node.props, children: kids === undefined ? undefined : expand(kids, `${path}>${node.type}`) } }
  }
  const api = {
    tree: null,
    render() {
      for (let round = 0; round < 5; round++) {
        api.tree = expand(el, '')
        const effects = [...states.values()].flatMap(c => c.effects.splice(0))
        if (!effects.length) break
        effects.forEach(f => f())
      }
      return api.tree
    },
    async settle(n = 8) {
      for (let i = 0; i < n; i++) await new Promise(r => setTimeout(r, 0))
      return api.render()
    },
  }
  api.render()
  return api
}
export function all(tree, pred, out = []) {
  if (Array.isArray(tree)) { tree.forEach(t => all(t, pred, out)); return out }
  if (!tree || typeof tree !== 'object') return out
  if (pred(tree)) out.push(tree)
  all(tree.props.children, pred, out)
  return out
}
export const text = t => (Array.isArray(t) ? t.map(text).join('') : t && typeof t === 'object' ? text(t.props.children) : t === null || t === undefined || t === false ? '' : String(t))
export const byText = (tree, type, re) => all(tree, n => n.type === type && re.test(text(n)))
export const one = (list, what) => { if (list.length !== 1) throw new Error(`${what}: found ${list.length}`); return list[0] }
export const button = (tree, re) => one(byText(tree, 'button', re), `button ${re}`)
export const ev = extra => ({ preventDefault() {}, stopPropagation() {}, ...extra })
export { host, queryClient }
const esc = v => String(v).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;')
const css = st => Object.entries(st).map(([k, v]) => `${k.startsWith('--') ? k : k.replace(/[A-Z]/g, c => '-' + c.toLowerCase())}:${typeof v === 'number' ? v + 'px' : v}`).join(';')
/** Static HTML of a rendered tree (for the browser check): string elements only, no handlers. */
export function toHtml(t) {
  if (Array.isArray(t)) return t.map(toHtml).join('')
  if (t === null || t === undefined || t === false) return ''
  if (typeof t !== 'object') return esc(t)
  const attrs = Object.entries(t.props).filter(([k, v]) => k !== 'children' && typeof v !== 'function' && v !== undefined && v !== null && v !== false)
    .map(([k, v]) => k === 'className' ? ` class="${esc(v)}"` : k === 'style' ? ` style="${esc(css(v))}"` : ` ${k === 'tabIndex' ? 'tabindex' : k}="${esc(v)}"`).join('')
  return `<${t.type}${attrs}>${toHtml(t.props.children)}</${t.type}>`
}
"""


DATA = r"""
const sw = (draw, auto) => ({ draw, auto })
export const DECKS = { ok: true, schema: 1, broken: {}, autodraw: { on: false, decks: ['agent-unblock'], threshold: 3 }, decks: [
  { deck: 'agent-unblock', name: 'Agent unblock', mark: 'square', source: 'shipped', cards: 20, auto_cards: 20, switch: sw(true, true) },
  { deck: 'coding', name: 'Coding', mark: 'circle', source: 'shipped', cards: 9, switch: sw(true, false) },
  { deck: 'writing', name: 'Writing', mark: 'diamond', source: 'shipped', cards: 8, switch: sw(true, false) },
  { deck: 'night-shift', name: 'Night shift', mark: 'ring', source: 'imported', cards: 1, switch: sw(true, false) },
  { deck: 'mine', name: 'Mine', mark: 'half', source: 'own', cards: 1, switch: sw(true, false) },
] }
export const MINE = { ok: true, schema: 1, deck: { deck: 'mine', name: 'Mine', mark: 'half', source: 'own', version: 2, license: 'own', by: 'Me',
  editable: true, edits_save_as: 'mine', cards: [{ id: 'mi-01', human: 'Say it out loud once.', agent: 'Write the goal in one sentence.', tags: ['own'], stats: {} }] } }
export const NIGHT = { ok: true, schema: 1, deck: { ...MINE.deck, deck: 'night-shift', name: 'Night shift', source: 'imported', license: 'CC0-1.0', by: 'Someone', edits_save_as: 'night-shift' } }
export const SETTINGS = { ok: true, schema: 1, settings: { autodraw: false, autodraw_threshold: 3, autodraw_per_turn: 1, autodraw_decks: ['agent-unblock', 'coding'],
  card_of_day: true, learning: true, show_in_sidebar: true } }
export const CARD = { deck: 'coding', deck_name: 'Coding', mark: 'circle', id: 'co-03', human: 'Read the error as a stranger.', agent: 'Quote the exact error line, then list two readings.', tags: ['auto'], directive: '::card{deck="coding" id="co-03"}' }
export const K = (...rest) => ['unblockbruecke', 'test', ...rest]
"""

WINDOW = "globalThis.window = { location: { hash: '#/unblockbruecke' }, addEventListener() {}, removeEventListener() {} }\n"


def run_js(tmp_path: Path, body: str, name: str = "case") -> dict:
    """Bundle `body` (an ES module with top-level await that imports from '@src/...', './helpers.js'
    and './data.js') against the stand-ins, run it in node, and return the JSON it prints last."""
    work = tmp_path / name
    work.mkdir()
    for file, text in (("sdk.js", SDK), ("react.js", REACT), ("jsx.js", JSX), ("helpers.js", HELPERS), ("data.js", DATA),
                       ("window.js", WINDOW)):
        (work / file).write_text(text, encoding="utf-8")
    code = "import './window.js'\n" + textwrap.dedent(body).replace("@src/", str(SRC) + "/")
    (work / "case.mjs").write_text(code, encoding="utf-8")
    script = work / "build.mjs"
    script.write_text(
        "import { createRequire } from 'module'\n"
        f"const require = createRequire({json.dumps(str(MODULES / 'esbuild' / 'package.json'))})\n"
        "const esbuild = require('esbuild')\n"
        f"const w = {json.dumps(str(work))}\n"
        "await esbuild.build({ entryPoints: [w + '/case.mjs'], bundle: true, format: 'esm', platform: 'node', target: 'node20',\n"
        "  outfile: w + '/out.mjs', logLevel: 'error', alias: { '@hermes/plugin-sdk': w + '/sdk.js', 'react/jsx-runtime': w + '/jsx.js',\n"
        "  react: w + '/react.js' } })\n", encoding="utf-8")
    built = subprocess.run([NODE, str(script)], capture_output=True, text=True, timeout=120)
    assert built.returncode == 0, built.stderr[-3000:]
    run = subprocess.run([NODE, str(work / "out.mjs")], capture_output=True, text=True, timeout=120)
    if run.returncode:
        print(run.stdout[-2000:], run.stderr[-3000:], sep="\n")
    assert run.returncode == 0, "the case failed in node; its output is above"
    return json.loads(run.stdout.strip().splitlines()[-1])


# ---- UI-12: a server error reads as a sentence ------------------------------------------------------

def test_server_errors_read_as_a_sentence_not_the_raw_answer(tmp_path):
    """UI-12: "Internal Server Error" and FastAPI's detail JSON never reach the user; contract messages do."""
    out = run_js(tmp_path, """
        import { restError, setCtx } from '@src/core.js'
        import { drawCard } from '@src/state.js'
        import { CardsPage } from '@src/page.js'
        import { JournalView } from '@src/journal.js'
        import { jsx } from 'react/jsx-runtime'
        import { fakeCtx, setAnswer, mount, text, queryClient } from './helpers.js'
        import { K } from './data.js'
        const m = e => restError(new Error(e)).message
        const msgs = {
          raw500: m("Error invoking remote method 'hermes:api': Error: 500: Internal Server Error"),
          detail422: m('422: ' + JSON.stringify({ detail: [{ type: 'int_parsing', loc: ['query', 'limit'], msg: 'bad' }] })),
          contract409: m('409: ' + JSON.stringify({ ok: false, schema: 1, error: 'no_card', message: 'no card fits' })),
          notOn: m('404: ' + JSON.stringify({ detail: 'Plugin not found' })),
          internal500: m('500: ' + JSON.stringify({ ok: false, schema: 1, error: 'internal', message: 'the plugin hit an unexpected error; the gateway log has the details' })),
        }
        const ctx = fakeCtx()
        setCtx(ctx)
        setAnswer(() => ({ __status: 500, body: 'Internal Server Error' }))
        await drawCard({})
        const raw = restError(new Error('500: Internal Server Error'))
        queryClient.setQueryData(K('decks'), raw)
        const page = text(mount(jsx(CardsPage, {})).tree)
        queryClient.setQueryData(K('journal', 'all', 50), raw)
        const journal = text(mount(jsx(JournalView, {})).tree)
        console.log(JSON.stringify({ msgs, toasts: globalThis.__toasts, page, journal }))
    """)
    m = out["msgs"]
    assert "Internal Server Error" not in m["raw500"] and "try again" in m["raw500"].lower()
    assert "[{" not in m["detail422"] and "int_parsing" not in m["detail422"] and "try again" in m["detail422"].lower()
    assert m["contract409"] == "no card fits"
    assert "is off in this Hermes profile" in m["notOn"]
    assert m["internal500"].startswith("the plugin hit an unexpected error")
    assert out["toasts"] and out["toasts"][-1].startswith("Could not draw: ") and "Internal Server Error" not in out["toasts"][-1]
    assert "The decks did not load: " in out["page"] and "Internal Server Error" not in out["page"]
    assert "The journal did not load: " in out["journal"] and "Internal Server Error" not in out["journal"]


# ---- UI-20, UI-23, UI-24: copy ----------------------------------------------------------------------

LONGEST = r"""
export function leaves(t, out = []) {
  if (Array.isArray(t)) { t.forEach(x => leaves(x, out)); return out }
  if (t && typeof t === 'object') { for (const k of ['title', 'aria-label', 'description']) if (typeof t.props[k] === 'string') out.push(t.props[k]); leaves(t.props.children, out); return out }
  if (typeof t === 'string') out.push(t)
  return out
}
"""


def test_no_visible_string_over_160_characters_and_deck_names_not_slugs(tmp_path):
    """UI-20, UI-23: the decks note, the settings page and the connection notes stay under 160
    characters per string, and they name decks by their name ("Agent unblock"), never the slug."""
    out = run_js(tmp_path, """
        import { NOT_ON_TEXT, OFFLINE_TEXT, SCHEMA_TEXT } from '@src/core.js'
        import { DecksView } from '@src/decks.js'
        import { SettingsPage } from '@src/settings.js'
        import { jsx } from 'react/jsx-runtime'
        import { mount, text, queryClient } from './helpers.js'
        import { DECKS, MINE, SETTINGS, K } from './data.js'
        """ + LONGEST.replace("export ", "") + """
        queryClient.setQueryData(K('deck', 'agent-unblock'), { ok: true, schema: 1, deck: { ...MINE.deck, deck: 'agent-unblock', name: 'Agent unblock', source: 'shipped', license: 'CC0-1.0' } })
        queryClient.setQueryData(K('decks'), DECKS)
        queryClient.setQueryData(K('settings'), SETTINGS)
        const off = mount(jsx(DecksView, { decksData: DECKS })).tree
        const on = mount(jsx(DecksView, { decksData: { ...DECKS, autodraw: { on: true, decks: ['agent-unblock', 'coding'], threshold: 3 } } })).tree
        const settings = mount(jsx(SettingsPage, {})).tree
        const strings = [NOT_ON_TEXT, OFFLINE_TEXT, SCHEMA_TEXT, ...leaves(off), ...leaves(on), ...leaves(settings)]
        console.log(JSON.stringify({ long: strings.filter(s => [...s].length > 160), off: text(off), on: text(on), settings: text(settings) }))
    """)
    assert out["long"] == []
    for view in ("off", "on", "settings"):
        assert "agent-unblock" not in out[view].replace("Auto-draw from Agent unblock", ""), out[view]
        assert "Agent unblock" in out[view]
    assert "Coding" in out["settings"]


def test_card_of_the_day_date_is_a_local_day_and_the_own_license_badge_is_gone(tmp_path):
    """UI-23: the chip prints the card-of-the-day date through the local formatter (not "2026-11-10").
    UI-24: an own deck's header shows "yours" once, not the license id "own" beside it."""
    out = run_js(tmp_path, """
        import { Chip } from '@src/chip.js'
        import { DecksView } from '@src/decks.js'
        import { jsx } from 'react/jsx-runtime'
        import { mount, text, all, queryClient } from './helpers.js'
        import { DECKS, MINE, NIGHT, CARD, K } from './data.js'
        const now = new Date()
        const iso = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
        queryClient.setQueryData(K('today'), { ok: true, schema: 1, enabled: true, date: iso, card: CARD })
        const { $popOpen } = await import('@src/state.js')
        $popOpen.set(true)
        const chip = text(mount(jsx(Chip, {})).tree)
        queryClient.setQueryData(K('today'), { ok: true, schema: 1, enabled: true, date: '2026-03-02', card: CARD })
        const old = text(mount(jsx(Chip, {})).tree)
        const badges = slug => {
          queryClient.setQueryData(K('deck', slug), slug === 'mine' ? MINE : NIGHT)
          const v = mount(jsx(DecksView, { decksData: { ...DECKS, decks: DECKS.decks.filter(d => d.deck === slug) } }))
          return all(v.tree, n => n.type === 'span' && /badge/.test(n.props.className || '')).map(text)
        }
        console.log(JSON.stringify({ chip, iso, old, mine: badges('mine'), night: badges('night-shift') }))
    """)
    assert out["iso"] not in out["chip"] and "Card of the day" in out["chip"] and "Today" in out["chip"]
    assert "2 Mar" in out["old"] and "2026-03-02" not in out["old"]
    assert "own" not in out["mine"] and "yours" in out["mine"], out["mine"]
    assert "CC0-1.0" in out["night"] and "imported" in out["night"]


# ---- UI-18: "Hermes drew" belongs to the chat it happened in ------------------------------------------

def test_hermes_drew_clears_when_another_chat_gets_focus(tmp_path):
    """UI-18: the chip's "Hermes drew <id> in this chat" goes away as soon as the focused chat changes."""
    out = run_js(tmp_path, """
        import { Chip } from '@src/chip.js'
        import { jsx } from 'react/jsx-runtime'
        import { mount, text, host, queryClient } from './helpers.js'
        import { CARD, K } from './data.js'
        const auto = (draws) => ({ ok: true, schema: 1, draws, totals: {}, learning: true })
        const drew = { draw_id: 'd-9', card: 'ag-16', deck: 'agent-unblock', at: new Date().toISOString(), view: { ...CARD, id: 'ag-16', deck: 'agent-unblock', deck_name: 'Agent unblock' } }
        queryClient.setQueryData(K('today'), { ok: true, schema: 1, enabled: true, date: '2026-11-10', card: CARD })
        host.state.focusedStoredSessionId.set('chat-a')
        queryClient.setQueryData(K('journal', 'auto', 'chat-a'), auto([]))
        const view = mount(jsx(Chip, {}))
        const before = text(view.render())
        queryClient.setQueryData(K('journal', 'auto', 'chat-a'), auto([drew]))
        const live = text(view.render())
        host.state.focusedStoredSessionId.set('chat-b')
        queryClient.setQueryData(K('journal', 'auto', 'chat-b'), auto([]))
        const other = text(view.render())
        host.state.focusedStoredSessionId.set(null)
        const none = text(view.render())
        console.log(JSON.stringify({ before, live, other, none }))
    """)
    assert "Hermes drew" not in out["before"]
    assert "Hermes drew ag-16" in out["live"]
    assert "Hermes drew" not in out["other"], out["other"]
    assert "Hermes drew" not in out["none"], out["none"]
    assert CARD_HUMAN in out["other"]


CARD_HUMAN = "Read the error as a stranger."


# ---- UI-22: the shortcut draws from what the table shows ----------------------------------------------

def test_shortcut_uses_the_table_deck_choice_and_falls_back_quietly(tmp_path):
    """UI-22: mod+alt+u draws from the last deck only while it is switched on for drawing; a switched-off
    or deleted deck falls back to Any deck without a toast per press, and deleting a deck forgets it."""
    out = run_js(tmp_path, """
        import plugin from '@src/index.js'
        import { DecksView } from '@src/decks.js'
        import { jsx } from 'react/jsx-runtime'
        import { fakeCtx, setAnswer, rests, mount, all, button, queryClient } from './helpers.js'
        import { DECKS, MINE, SETTINGS, CARD, K } from './data.js'
        const decks = { ...DECKS, decks: DECKS.decks.map(d => (d.deck === 'writing' ? { ...d, switch: { draw: false, auto: false } } : d)) }
        setAnswer((m, p) => {
          if (m === 'GET' && p === '/decks') return decks
          if (m === 'GET' && p === '/settings') return SETTINGS
          if (m === 'POST' && p === '/draw') return { ok: true, schema: 1, card: CARD, draw_id: 'd-' + rests.length }
          if (m === 'POST' && p.endsWith('/delete')) return { ok: true, schema: 1, deck: 'mine', undo: { restore: 2 } }
          return { ok: true, schema: 1 }
        })
        const ctx = fakeCtx()
        plugin.register(ctx)
        await new Promise(r => setTimeout(r, 20))
        const key = ctx.reg.find(c => c.id === 'draw-key').data
        const press = async deck => {
          ctx.storage.set('deck', deck)
          const n = rests.length
          await key.run()
          await new Promise(r => setTimeout(r, 5))
          const sent = rests.slice(n).filter(([m, p]) => m === 'POST' && p === '/draw').map(r => r[2].deck || null)
          return { sent, kept: ctx.storage.get('deck', '') }
        }
        const res = { off: await press('writing'), again: await press(''), gone: await press('no-such-deck'), on: await press('coding') }
        res.toasts = globalThis.__toasts.slice()
        ctx.storage.set('deck', 'mine')
        queryClient.setQueryData(K('deck', 'mine'), MINE)
        const view = mount(jsx(DecksView, { decksData: { ...DECKS, decks: DECKS.decks.filter(d => d.deck === 'mine') } }))
        button(view.tree, /^Delete deck$/).props.onClick()
        const dialog = all(view.render(), n => n.type === 'ConfirmDialog' && n.props.open)[0]
        await dialog.props.onConfirm()
        res.afterDelete = ctx.storage.get('deck', '')
        console.log(JSON.stringify(res))
    """)
    assert out["off"] == {"sent": [None], "kept": ""}, out
    assert out["again"]["sent"] == [None]
    assert out["gone"] == {"sent": [None], "kept": ""}, out
    assert out["on"] == {"sent": ["coding"], "kept": "coding"}, out
    assert out["toasts"] == [], out["toasts"]
    assert out["afterDelete"] == ""


# ---- the decks editor -------------------------------------------------------------------------------

EDITOR = r"""
import { DecksView } from '@src/decks.js'
import { setCtx } from '@src/core.js'
import { jsx } from 'react/jsx-runtime'
import { fakeCtx, setAnswer, rests, mount, all, one, text, button, ev, queryClient } from './helpers.js'
import { DECKS, MINE, K } from './data.js'
setCtx(fakeCtx())
queryClient.setQueryData(K('deck', 'agent-unblock'), { ...MINE, deck: { ...MINE.deck, deck: 'agent-unblock', name: 'Agent unblock', source: 'shipped' } })
queryClient.setQueryData(K('deck', 'mine'), MINE)
const view = mount(jsx(DecksView, { decksData: DECKS }))
const field = label => one(all(view.tree, n => n.props['aria-label'] === label), label)
const type = (label, value) => { field(label).props.onChange({ target: { value } }); return view.render() }
const posts = () => rests.filter(([m]) => m !== 'GET').map(([m, p, b]) => [m, p, b])
"""


def test_new_deck_refuses_a_taken_name_and_waits_for_a_valid_one(tmp_path):
    """UI-04: New deck never edits or copies an existing deck: a name or file name already taken is
    refused with a plain message. UI-15: "Preview the new deck" stays disabled until the name is valid."""
    out = run_js(tmp_path, EDITOR + """
        setAnswer(() => ({ ok: true, schema: 1, target: 'fresh-deck', summary: '1 card added', cards: 1, confirm: 'c1', diff: {} }))
        button(view.tree, /^New deck$/).props.onClick()
        view.render()
        type('Human face', 'Start with the smallest thing.')
        type('Agent face', 'Write the smallest next step and do only that.')
        const state = () => {
          const b = button(view.tree, /^Preview the new deck$/)
          return { disabled: !!b.props.disabled, note: text(all(view.tree, n => n.props['data-ubk'] === 'new-deck')) }
        }
        const res = { empty: state() }
        type('Deck name', 'Coding'); res.slugTaken = state()
        type('Deck name', 'coding'); res.lower = state()
        type('Deck name', 'Night shift two'); type('File name', 'night-shift'); res.fileTaken = state()
        type('File name', ''); type('Deck name', 'Mine'); res.nameTaken = state()
        type('Deck name', 'Fresh deck'); res.fresh = state()
        const before = posts().length
        button(view.tree, /^Preview the new deck$/).props.onClick()
        await view.settle()
        res.sent = posts().slice(before)
        res.preview = all(view.tree, n => n.props['data-ubk'] === 'preview').length
        console.log(JSON.stringify(res))
    """)
    assert out["empty"]["disabled"] is True
    for k in ("slugTaken", "lower", "fileTaken", "nameTaken"):
        assert out[k]["disabled"] is True, k
        assert "taken" in out[k]["note"] or "already" in out[k]["note"], (k, out[k]["note"])
    assert out["fresh"]["disabled"] is False and "taken" not in out["fresh"]["note"]
    assert out["sent"][0][0:2] == ["POST", "/decks/fresh-deck/preview"] and out["preview"] == 1


def test_replace_mine_asks_first_and_offers_undo(tmp_path):
    """UI-21: "Replace mine" opens a confirm before anything is written; after the replace the Undo bar
    restores the user's own version (lane AGENT answers `undo` like a save does)."""
    out = run_js(tmp_path, EDITOR + """
        let replaced = false
        setAnswer((m, p, b) => {
          if (p === '/decks/import' && !b.replace) return { __status: 409, body: { ok: false, schema: 1, error: 'exists', message: 'a deck named mine is already there' } }
          if (p === '/decks/import') { replaced = true; return { ok: true, schema: 1, deck: 'mine', source: 'imported', cards: 1, version: 3, replaced: true, undo: { restore: 2 } } }
          if (p === '/decks/mine/restore') return { ok: true, schema: 1, deck: 'mine', restored: 2, summary: 'back' }
          return { ok: true, schema: 1 }
        })
        const file = { name: 'mine.yaml', size: 40, text: async () => 'deck: mine' }
        field('Deck file').props.onChange({ target: { files: [file], value: 'x' } })
        await view.settle()
        button(view.tree, /^Replace mine$/).props.onClick()
        view.render()
        const dialog = all(view.tree, n => n.type === 'ConfirmDialog' && n.props.open && /Replace/.test(n.props.title || ''))
        const res = { dialogs: dialog.length, title: dialog[0] && dialog[0].props.title, writtenBeforeConfirm: replaced }
        await dialog[0].props.onConfirm()
        await view.settle()
        res.undoBar = text(all(view.tree, n => n.props['data-ubk'] === 'undo'))
        button(view.tree, /^Undo$/).props.onClick()
        await view.settle()
        res.sent = posts().map(([m, p, b]) => [p, b.replace || false, b.version || null])
        console.log(JSON.stringify(res))
    """)
    assert out["dialogs"] == 1 and out["writtenBeforeConfirm"] is False, out
    assert "Undo" in out["undoBar"], out["undoBar"]
    assert out["sent"] == [["/decks/import", False, None], ["/decks/import", True, None], ["/decks/mine/restore", False, 2]], out["sent"]


def test_problem_lists_show_at_most_fifty_and_say_how_many_more(tmp_path):
    """UI-06: a refusal with thousands of problems renders the capped list plus "and N more", both for
    the capped answer lane CORE sends (problems_more) and for an older uncapped one."""
    out = run_js(tmp_path, EDITOR + """
        const probs = n => Array.from({ length: n }, (_, i) => ({ card: `bg-${i}`, rule: 'tags', message: 'unknown tag nope' }))
        let mode = 'capped'
        setAnswer((m, p) => {
          if (p === '/decks/import') return { __status: 422, body: mode === 'capped'
            ? { ok: false, schema: 1, error: 'invalid_deck', message: 'the deck breaks 4902 rules', problems: probs(50), problems_more: 4852 }
            : { ok: false, schema: 1, error: 'invalid_deck', message: 'the deck breaks 60 rules', problems: probs(60) } }
          return { ok: true, schema: 1 }
        })
        const pick = async () => {
          field('Deck file').props.onChange({ target: { files: [{ name: 'big.yaml', size: 40, text: async () => 'deck: big' }], value: 'x' } })
          await view.settle()
          const list = all(view.tree, n => n.type === 'ul' && /problems/.test(n.props.className || ''))[0]
          return { items: all(list, n => n.type === 'li').length, text: text(all(view.tree, n => n.props['data-ubk'] === 'import')) }
        }
        const capped = await pick()
        mode = 'old'
        const old = await pick()
        console.log(JSON.stringify({ capped, old }))
    """)
    assert out["capped"]["items"] == 50 and "and 4852 more" in out["capped"]["text"], out["capped"]["items"]
    assert out["old"]["items"] == 50 and "and 10 more" in out["old"]["text"]


def test_escape_cancels_the_card_editor_the_preview_and_new_deck(tmp_path):
    """UI-13: Escape works as Cancel in the card editor, the preview panel and the New deck form."""
    out = run_js(tmp_path, EDITOR + """
        setAnswer(() => ({ ok: true, schema: 1, target: 'mine', summary: '1 card removed', cards: 0, confirm: 'c1', diff: {} }))
        const count = id => all(view.tree, n => n.props['data-ubk'] === id).length
        const escape = id => { one(all(view.tree, n => n.props['data-ubk'] === id && n.props.onKeyDown), id).props.onKeyDown(ev({ key: 'Escape' })); return view.render() }
        one(all(view.tree, n => n.type === 'button' && n.props.className === 'nm' && text(n) === 'Mine'), 'Mine').props.onClick()
        view.render()
        const res = {}
        all(view.tree, n => n.props['aria-label'] === 'Edit mi-01')[0].props.onClick(); view.render()
        res.editorOpen = count('card-editor')
        escape('card-editor'); res.editorAfter = count('card-editor')
        all(view.tree, n => n.props['aria-label'] === 'Remove mi-01')[0].props.onClick(); await view.settle()
        res.previewOpen = count('preview')
        escape('preview'); res.previewAfter = count('preview')
        button(view.tree, /^New deck$/).props.onClick(); view.render()
        res.newOpen = count('new-deck')
        escape('new-deck'); res.newAfter = count('new-deck')
        console.log(JSON.stringify(res))
    """)
    assert out == {"editorOpen": 1, "editorAfter": 0, "previewOpen": 1, "previewAfter": 0, "newOpen": 1, "newAfter": 0}, out


def test_card_length_counts_characters_as_the_backend_does(tmp_path):
    """UI-14: 46 emoji are 46 characters (Python's len()), not 92 UTF-16 units: Preview stays enabled."""
    out = run_js(tmp_path, EDITOR + """
        one(all(view.tree, n => n.type === 'button' && n.props.className === 'nm' && text(n) === 'Mine'), 'Mine').props.onClick()
        view.render()
        button(view.tree, /^New card$/).props.onClick(); view.render()
        const look = () => ({ label: text(all(view.tree, n => n.props['data-ubk'] === 'card-editor')[0]).match(/Human face \\(\\d+\\/90\\)/)[0],
          disabled: !!button(view.tree, /^Preview$/).props.disabled, max: field('Human face').props.maxLength || null })
        type('Agent face', 'Name the joker in this plan, then remove it.')
        type('Human face', '\\u{1F0CF}'.repeat(46))
        const ok = look()
        type('Human face', '\\u{1F0CF}'.repeat(91))
        const over = look()
        console.log(JSON.stringify({ ok, over }))
    """)
    assert out["ok"]["label"] == "Human face (46/90)" and out["ok"]["disabled"] is False, out
    assert out["ok"]["max"] is None or out["ok"]["max"] >= 180
    assert out["over"]["label"] == "Human face (91/90)" and out["over"]["disabled"] is True


# ---- UI-11, UI-10: the card's text -------------------------------------------------------------------

def test_card_lines_and_table_text_take_their_direction_from_the_text(tmp_path):
    """UI-11: card lines, the editor's table cells and the journal's card text carry dir="auto", so an
    Arabic or Hebrew line reads right to left."""
    out = run_js(tmp_path, EDITOR + """
        import { Card } from '@src/ui.js'
        import { JournalView } from '@src/journal.js'
        const card = mount(jsx(Card, { card: { deck: 'x', id: 'xx-01', human: 'اقرأ رسالة الخطأ', agent: 'כתוב את שורת השגיאה', tags: [] }, flipped: false })).tree
        const dirs = cls => all(card, n => (n.props.className || '').split(' ').includes(cls)).map(n => n.props.dir || null)
        one(all(view.tree, n => n.type === 'button' && n.props.className === 'nm' && text(n) === 'Mine'), 'Mine').props.onClick()
        view.render()
        const cells = cls => all(view.tree, n => n.type === 'td' && n.props.className === cls).map(n => n.props.dir || null)
        queryClient.setQueryData(K('journal', 'all', 50), { ok: true, schema: 1, learning: true, totals: {}, draws: [
          { draw_id: 'd1', at: new Date().toISOString(), by: 'user', deck: 'x', card: 'xx-01', view: { human: 'اقرأ', deck_name: 'X' } }] })
        const journal = mount(jsx(JournalView, {})).tree
        console.log(JSON.stringify({ line: dirs('f-line'), instr: dirs('f-instr'), hf: cells('hf'), af: cells('af'),
          jcard: all(journal, n => n.type === 'td' && n.props.className === 'jcard').map(n => n.props.dir || null) }))
    """)
    assert out == {"line": ["auto"], "instr": ["auto"], "hf": ["auto"], "af": ["auto"], "jcard": ["auto"]}, out


PLAYWRIGHT = os.environ.get("UBK_PLAYWRIGHT", "")
CHROME = os.environ.get("UBK_CHROME", "")


@pytest.mark.skipif(not (PLAYWRIGHT and CHROME), reason="set UBK_PLAYWRIGHT (the playwright module folder) and UBK_CHROME to run the browser check")
def test_cards_fit_text_at_the_contract_limits_in_a_browser(tmp_path):
    """UI-10: the 200 px card (popover, transcript) and the 300 px table card fit a 90-character human
    line, a 220-character instruction, four 20-character tags and a 40-character deck name: no face
    content runs past its box, and the bottom row stays inside the inner frame line. UI-11 in a real
    layout engine: an Arabic line computes to direction rtl."""
    out = run_js(tmp_path, f"""
        import {{ Card }} from '@src/ui.js'
        import {{ installStyle }} from '@src/style.js'
        import {{ jsx }} from 'react/jsx-runtime'
        import {{ mount, toHtml }} from './helpers.js'
        const {{ createRequire }} = await import('module')
        const req = createRequire(import.meta.url)
        let sheet = ''
        globalThis.document = {{ createElement: () => ({{ setAttribute() {{}} }}), head: {{ appendChild: n => {{ sheet = n.textContent }} }} }}
        installStyle()
        const fit = (s, n) => (s + ' and then one more step').repeat(4).replace(/\\s+/g, ' ').slice(0, n - 1).replace(/ $/, 'x') + '.'
        const card = {{ deck: 'long', id: 'lo-01', mark: 'ring', human: fit('Ask the newest person on the team what they would delete first and then delete half of it now', 90),
          agent: fit('List every assumption the last three attempts shared, write each as a sentence that could be false, pick the cheapest one to test, run exactly one check against it, and report what the check showed before any other change at all', 220),
          deck_name: fit('A deck with a name right at the limit ok', 40), tags: ['premise-checking-tag1', 'assumptions-ledgerxx', 'auto', 'human'] }}
        const rtl = {{ ...card, id: 'rt-01', human: 'اقرأ رسالة الخطأ كما لو كنت غريبًا عنها، ثم قل ما تعنيه.' }}
        const html = [[card, 200, 'sm'], [card, 300, undefined], [rtl, 300, undefined]].map(([c, width, size]) =>
          `<div class="ubk" style="padding:20px">${{toHtml(mount(jsx(Card, {{ card: c, flipped: false, width, size }})).tree)}}</div>`).join('')
        const {{ chromium }} = req({json.dumps(PLAYWRIGHT)})
        const browser = await chromium.launch({{ executablePath: {json.dumps(CHROME)}, headless: true, args: ['--no-sandbox'] }})
        const page = await browser.newPage({{ viewport: {{ width: 900, height: 1400 }} }})
        await page.setContent(`<!doctype html><html><head><meta charset="utf-8"><style>${{sheet}}</style></head><body>${{html}}</body></html>`)
        const faces = await page.evaluate(() => [...document.querySelectorAll('.ubk-card .face')].map(el => {{
          const box = el.getBoundingClientRect()
          const bot = el.querySelector('.f-bot').getBoundingClientRect()
          return {{ w: Math.round(box.width), kind: el.classList.contains('agent') ? 'agent' : 'human', over: el.scrollHeight - el.clientHeight,
            foot: Math.round(bot.bottom - (box.bottom - box.width * 0.032)),
            spare: (cs => Math.round(parseFloat(cs.marginTop) + parseFloat(cs.marginBottom)))(getComputedStyle(el.querySelector('.f-line, .f-instr'))) }}
        }}))
        const dir = await page.evaluate(() => getComputedStyle(document.querySelectorAll('.ubk-card .f-line')[2]).direction)
        await browser.close()
        console.log(JSON.stringify({{ faces, dir }}))
    """)
    print("faces", out["faces"])  # spare: the px the auto margins around the text still have
    for f in out["faces"]:
        assert f["over"] <= 1 and f["foot"] <= 0, out["faces"]
        # Headroom for the Mac's serif (New York is wider than the Linux fallback this runs with).
        assert f["spare"] >= 12, out["faces"]
    assert len(out["faces"]) == 6 and out["dir"] == "rtl"
