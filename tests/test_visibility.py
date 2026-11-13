"""Show and hide: the Draw button follows show_in_statusbar on every GET /settings read;
the sidebar row comes from the shared module and its retired key show_in_sidebar seeds it once
(the same module in every Studio Luftbrücke plugin). Driven in node through the stand-ins in
test_page.py.

Skipped without node and desktop/build/node_modules, like test_page.py.
"""
import pytest

from test_page import MODULES, NODE, run_js

pytestmark = pytest.mark.skipif(not NODE or not (MODULES / "esbuild").is_dir(),
                                reason="node and desktop/build/node_modules (npm ci) are needed to run desktop/src")

CASE = """
import plugin from '@src/index.js'
import { readVisibility, sidebarRow } from '@src/visibility.js'
import { SETTINGS } from './data.js'
// A ctx whose register() returns a real disposer, so the live set of contributions can be read.
// `stored` holds ctx.storage entries by key, as Desktop's local storage would after a restart.
const disposers = []
const makeCtx = (stored = {}) => {
  disposers.splice(0).forEach(d => d())
  const live = new Set()
  const store = new Map(Object.entries(stored))
  return {
    live, store,
    register: c => { live.add(c); return () => live.delete(c) },
    onDispose: d => disposers.push(d),
    rest: async (path, opts = {}) => { const out = await answer(opts.method || 'GET', path); if (out instanceof Error) throw out; return out },
    storage: { get: (k, d) => (store.has(k) ? store.get(k) : d), set: (k, v) => store.set(k, v) },
  }
}
let answer = () => ({})
const settings = (bar, side = true) => ({ ...SETTINGS, settings: { ...SETTINGS.settings, show_in_statusbar: bar, show_in_sidebar: side } })
// A backend that no longer sends show_in_sidebar.
const withoutKey = () => { const s = { ...SETTINGS.settings, show_in_statusbar: true }; delete s.show_in_sidebar; return { ...SETTINGS, settings: s } }
const items = ctx => [...ctx.live].filter(c => c.area === 'statusBar.right')
const rows = ctx => [...ctx.live].filter(c => c.area === 'sidebar.nav')
const view = ctx => rows(ctx).map(r => `${r.id}@${r.order}:${r.data.label}:${r.data.path}:${r.data.codicon}`).join(' ')
const tick = () => new Promise(r => setTimeout(r, 5))
// An answer the test releases by hand, so a user's choice can land while the first read is in flight.
const held = () => { let release; const p = new Promise(r => { release = r }); return { answer: () => p, release } }
"""
ROW = "nav@53:Unblockbrücke:/unblockbruecke:copy"


def test_the_button_follows_the_stored_answer_before_any_read_and_each_read_after(tmp_path):
    """RV6: before any read the button follows the stored answer (nothing stored or true: shown; false:
    not shown). A read answering false disposes it and stores false; turned true it registers once,
    and repeated reads do not register it twice. A failed read, the first one included, keeps the
    state. The sidebar row is there from the start, and reads after the first leave it alone."""
    out = run_js(tmp_path, CASE + """
        const res = {}
        for (const [name, stored] of [['nothing', {}], ['true', { show_in_statusbar: true }], ['false', { show_in_statusbar: false }]]) {
          answer = () => new Error('offline')
          const ctx = makeCtx(stored)
          plugin.register(ctx)
          res[name] = { before: items(ctx).length, rows: rows(ctx).length }
          await tick()
          res[name].afterFailedFirstRead = items(ctx).length
        }
        const ctx = makeCtx()
        answer = (m, p) => settings(false)
        plugin.register(ctx)
        await tick()
        res.off = { items: items(ctx).length, stored: ctx.store.get('show_in_statusbar'), rows: rows(ctx).length }
        answer = (m, p) => settings(true, false)
        await readVisibility(); await readVisibility(); await readVisibility()
        res.on = { items: items(ctx).length, stored: ctx.store.get('show_in_statusbar'), rows: rows(ctx).length }
        answer = () => new Error('offline')
        await readVisibility()
        res.failed = { items: items(ctx).length, stored: ctx.store.get('show_in_statusbar') }
        answer = (m, p) => ({ ...SETTINGS, settings: { ...SETTINGS.settings } })
        await readVisibility()
        res.olderBackend = items(ctx).length
        const item = items(ctx)[0]
        res.item = { id: item.id, dataId: item.data.id, toggleLabel: item.data.toggleLabel, topRender: typeof item.render, dataRender: typeof item.data.render }
        console.log(JSON.stringify(res))
    """)
    assert out["nothing"] == {"before": 1, "rows": 1, "afterFailedFirstRead": 1}, out
    assert out["true"] == {"before": 1, "rows": 1, "afterFailedFirstRead": 1}, out
    assert out["false"] == {"before": 0, "rows": 1, "afterFailedFirstRead": 0}, out
    assert out["off"] == {"items": 0, "stored": False, "rows": 1}, out
    assert out["on"] == {"items": 1, "stored": True, "rows": 1}, out
    assert out["failed"] == {"items": 1, "stored": True}, out
    assert out["olderBackend"] == 1
    assert out["item"] == {"id": "statusbar", "dataId": "unblockbruecke.draw", "toggleLabel": "Unblockbrücke",
                           "topRender": "undefined", "dataRender": "function"}, out


def test_the_row_is_the_brand_at_53_from_the_first_frame(tmp_path):
    """The shared module registers the row in register(), before any backend answer: the brand as the
    label, the page path, the copy codicon, position 53. A stored position and a stored hidden
    row hold."""
    out = run_js(tmp_path, CASE + """
        const res = {}
        answer = () => new Promise(() => {})
        let ctx = makeCtx()
        plugin.register(ctx)
        res.fresh = view(ctx)
        ctx = makeCtx({ sidebar: { show: true, position: 12 } })
        plugin.register(ctx)
        res.moved = view(ctx)
        ctx = makeCtx({ sidebar: { show: false, position: 53 } })
        plugin.register(ctx)
        res.hidden = rows(ctx).length
        console.log(JSON.stringify(res))
    """)
    assert out == {"fresh": ROW, "moved": "nav@12:Unblockbrücke:/unblockbruecke:copy", "hidden": 0}, out


def test_seed_skipped_when_a_choice_is_stored(tmp_path):
    """A stored choice wins over the retired key, both ways: shown at 20 with the backend saying false
    stays shown at 20; hidden with the backend saying true stays hidden. Storage is not written."""
    out = run_js(tmp_path, CASE + """
        const res = {}
        for (const [name, stored, side] of [['shownBackendFalse', { show: true, position: 20 }, false], ['hiddenBackendTrue', { show: false, position: 53 }, true]]) {
          const ctx = makeCtx({ sidebar: stored })
          let sets = 0
          const set = ctx.storage.set
          ctx.storage.set = (k, v) => { if (k === 'sidebar') sets += 1; return set(k, v) }
          answer = () => new Promise(() => {})
          plugin.register(ctx)
          answer = () => settings(true, side)
          const read = await readVisibility()
          res[name] = { rows: view(ctx), stored: ctx.store.get('sidebar'), sets, seeded: read.seeded, sidebar: read.sidebar }
        }
        console.log(JSON.stringify(res))
    """)
    assert out["shownBackendFalse"] == {"rows": "nav@20:Unblockbrücke:/unblockbruecke:copy", "stored": {"show": True, "position": 20},
                                        "sets": 0, "seeded": False, "sidebar": True}, out
    assert out["hiddenBackendTrue"] == {"rows": "", "stored": {"show": False, "position": 53}, "sets": 0, "seeded": False,
                                        "sidebar": False}, out


def test_no_stored_choice_and_the_backend_says_false_hides_and_stores(tmp_path):
    """The row shows at start (the key's default), the first answer false hides it and stores
    {show: false, position: 53}; a later read saying true changes nothing; a restart with that
    storage starts hidden and seeds nothing."""
    out = run_js(tmp_path, CASE + """
        const res = {}
        let ctx = makeCtx()
        const first = held()
        answer = first.answer
        plugin.register(ctx)
        res.beforeAnswer = { rows: view(ctx), stored: ctx.store.has('sidebar') }
        first.release(settings(true, false))
        await tick()
        res.afterAnswer = { rows: rows(ctx).length, stored: ctx.store.get('sidebar'), prefs: sidebarRow().prefs() }
        answer = () => settings(true, true)
        const later = await readVisibility()
        res.laterRead = { rows: rows(ctx).length, seeded: later.seeded, stored: ctx.store.get('sidebar') }
        ctx = makeCtx({ sidebar: ctx.store.get('sidebar') })
        answer = () => settings(true, true)
        plugin.register(ctx)
        res.restartBefore = rows(ctx).length
        await tick()
        res.restartAfter = { rows: rows(ctx).length, stored: ctx.store.get('sidebar') }
        console.log(JSON.stringify(res))
    """)
    assert out["beforeAnswer"] == {"rows": ROW, "stored": False}, out
    assert out["afterAnswer"] == {"rows": 0, "stored": {"show": False, "position": 53}, "prefs": {"show": False, "position": 53}}, out
    assert out["laterRead"] == {"rows": 0, "seeded": False, "stored": {"show": False, "position": 53}}, out
    assert out["restartBefore"] == 0
    assert out["restartAfter"] == {"rows": 0, "stored": {"show": False, "position": 53}}, out


def test_no_stored_choice_and_the_backend_says_true_or_omits_the_key_stores_the_defaults(tmp_path):
    """A backend that still sends the key (true) and one that no longer sends it both store the
    defaults {show: true, position: 53}, with the row in place throughout. setPrefs alone would store
    nothing here (nothing changed), so the plugin stores them itself."""
    out = run_js(tmp_path, CASE + """
        const res = {}
        for (const [name, body] of [['sendsTrue', settings(true, true)], ['noKey', withoutKey()]]) {
          const ctx = makeCtx()
          answer = () => body
          plugin.register(ctx)
          const before = view(ctx)
          await tick()
          res[name] = { before, after: view(ctx), stored: ctx.store.get('sidebar'), keySent: 'show_in_sidebar' in body.settings }
        }
        console.log(JSON.stringify(res))
    """)
    assert out["sendsTrue"] == {"before": ROW, "after": ROW, "stored": {"show": True, "position": 53}, "keySent": True}, out
    assert out["noKey"] == {"before": ROW, "after": ROW, "stored": {"show": True, "position": 53}, "keySent": False}, out


def test_a_choice_made_while_the_first_read_is_in_flight_wins(tmp_path):
    """The seed re-reads storage when the answer arrives: a user who hid the row (backend: true) or
    moved it (backend: false) before the first answer keeps that choice."""
    out = run_js(tmp_path, CASE + """
        const res = {}
        for (const [name, choice, side] of [['hidBackendTrue', { show: false }, true], ['movedBackendFalse', { position: 30 }, false]]) {
          const ctx = makeCtx()
          const first = held()
          answer = first.answer
          plugin.register(ctx)
          sidebarRow().setPrefs(choice)
          first.release(settings(true, side))
          await tick()
          res[name] = { rows: view(ctx), stored: ctx.store.get('sidebar') }
        }
        console.log(JSON.stringify(res))
    """)
    assert out["hidBackendTrue"] == {"rows": "", "stored": {"show": False, "position": 53}}, out
    assert out["movedBackendFalse"] == {"rows": "nav@30:Unblockbrücke:/unblockbruecke:copy", "stored": {"show": True, "position": 30}}, out


def test_a_failed_first_read_seeds_nothing_and_the_next_answer_seeds(tmp_path):
    """A failed read is no answer: the row stays shown and nothing is stored; the next answer seeds."""
    out = run_js(tmp_path, CASE + """
        const ctx = makeCtx()
        answer = () => new Error('offline')
        plugin.register(ctx)
        await tick()
        const failed = { rows: rows(ctx).length, stored: ctx.store.has('sidebar') }
        answer = () => settings(true, false)
        const read = await readVisibility()
        console.log(JSON.stringify({ failed, seeded: read.seeded, rows: rows(ctx).length, stored: ctx.store.get('sidebar') }))
    """)
    assert out == {"failed": {"rows": 1, "stored": False}, "seeded": True, "rows": 0, "stored": {"show": False, "position": 53}}, out


def test_settings_page_has_the_sidebar_section_and_no_show_in_sidebar_line(tmp_path):
    """The settings page renders the shared Sidebar block (switch, position, hint, and the palette line
    while hidden) and no longer lists or names the retired key; its switch hides the row and stores."""
    out = run_js(tmp_path, CASE + """
        import { SettingsPage } from '@src/settings.js'
        import { jsx } from 'react/jsx-runtime'
        import { mount, text, all, queryClient } from './helpers.js'
        import { DECKS, K } from './data.js'
        const ctx = makeCtx({ sidebar: { show: true, position: 53 } })
        answer = () => new Promise(() => {})
        plugin.register(ctx)
        queryClient.setQueryData(K('decks'), DECKS)
        queryClient.setQueryData(K('settings'), { ...SETTINGS, settings: { ...SETTINGS.settings, show_in_statusbar: false } })
        const m = mount(jsx(SettingsPage, {}))
        const section = () => all(m.tree, n => n.props['data-sidebar-section'] === 'Unblockbrücke')
        const shown = { count: section().length, text: text(section()[0]) }
        const kv = null
        all(section()[0], n => n.type === 'Switch')[0].props.onCheckedChange(false)
        m.render()
        const hidden = { text: text(section()[0]), rows: rows(ctx).length, stored: ctx.store.get('sidebar') }
        console.log(JSON.stringify({ all: text(m.tree), kv: text(kv), shown, hidden }))
    """)
    assert out["shown"]["count"] == 1, out
    assert out["shown"]["text"] == "SidebarShow in the sidebarPositionLower numbers sit higher. Kanban is 50.", out["shown"]
    assert out["hidden"] == {"text": "SidebarShow in the sidebarPositionLower numbers sit higher. Kanban is 50."
                                     "Open it from the command palette: Open Unblockbrücke.",
                             "rows": 0, "stored": {"show": False, "position": 53}}, out["hidden"]
    # 0.2: the settings page is a pointer: Open Unblockbrücke, the Sidebar section, the update note.
    assert out["all"].startswith("Open Unblockbrücke"), out["all"]
    assert "Show in sidebar" not in out["all"] and "Auto-draw" not in out["all"], out["all"]


def test_palette_open_unblockbruecke_opens_the_page(tmp_path):
    """The hidden-row line names the palette row "Open Unblockbrücke": it opens the page. 0.2 names table:
    the palette has "Draw a card", "Open Unblockbrücke" and "Draw from <deck>", no "Open decks"."""
    out = run_js(tmp_path, CASE + """
        import './helpers.js'
        const ctx = makeCtx()
        answer = () => new Promise(() => {})
        plugin.register(ctx)
        const palette = [...ctx.live].filter(c => c.area === 'palette')
        const open = palette.find(c => c.data.label === 'Open Unblockbrücke')
        globalThis.__calls.length = 0
        open.data.run()
        console.log(JSON.stringify({ labels: palette.map(c => c.data.label), id: open.id, dataId: open.data.id, calls: globalThis.__calls }))
    """)
    assert out["labels"][:2] == ["Draw a card", "Open Unblockbrücke"] and "Open decks" not in out["labels"], out
    assert out["id"] == "palette-open" and out["dataId"] == "unblockbruecke.palette.open", out
    assert out["calls"] == [["navigate", "/unblockbruecke"]], out
