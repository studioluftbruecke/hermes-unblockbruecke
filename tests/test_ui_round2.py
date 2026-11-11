"""The Desktop half after the second review pass (round 2, lane UI): each test drives desktop/src in node
through the stand-ins in test_ui_review.py (same renderer, same `ctx.rest` fake, same deck data).

Skipped without node and desktop/build/node_modules, like test_ui_review.py.
"""
import pytest

from test_ui_review import EDITOR, MODULES, NODE, run_js

pytestmark = pytest.mark.skipif(not NODE or not (MODULES / "esbuild").is_dir(),
                                reason="node and desktop/build/node_modules (npm ci) are needed to run desktop/src")

HUMAN = "Start with the smallest thing."
AGENT = "Write the smallest next step and do only that."


# ---- P2-UI-06: the first-card draft survives the refusal line -----------------------------------------

def test_new_deck_draft_survives_typing_a_taken_name_letter_by_letter(tmp_path):
    """P2-UI-06: typing a taken name makes the refusal line come and go; the first card written below it
    stays as it was through every step."""
    out = run_js(tmp_path, EDITOR + f"""
        button(view.tree, /^New deck$/).props.onClick()
        view.render()
        type('Human face', {HUMAN!r})
        type('Agent face', {AGENT!r})
        const seen = []
        for (const name of ['Z', 'Zebra', 'Codi', 'Coding', 'Coding 2', 'Coding', 'Fresh deck']) {{
          type('Deck name', name)
          seen.push({{ name, human: field('Human face').props.value, agent: field('Agent face').props.value,
            refused: !!button(view.tree, /^Preview the new deck$/).props.disabled }})
        }}
        console.log(JSON.stringify(seen))
    """)
    for step in out:
        assert step["human"] == HUMAN and step["agent"] == AGENT, step
    assert [s["refused"] for s in out] == [True, False, False, True, False, True, False], out


# ---- P2-UI-05: Escape inside an IME composition -------------------------------------------------------

def test_escape_during_an_ime_composition_keeps_the_editor_and_the_form(tmp_path):
    """P2-UI-05: Escape that cancels an IME candidate (isComposing, or keyCode 229) closes nothing; a plain
    Escape still cancels."""
    out = run_js(tmp_path, EDITOR + """
        const count = id => all(view.tree, n => n.props['data-ubk'] === id).length
        const press = (id, extra) => { all(view.tree, n => n.props['data-ubk'] === id && n.props.onKeyDown).forEach(n => n.props.onKeyDown(ev({ key: 'Escape', ...extra }))); return view.render() }
        one(all(view.tree, n => n.type === 'button' && n.props.className === 'nm' && text(n) === 'Mine'), 'Mine').props.onClick()
        view.render()
        button(view.tree, /^New card$/).props.onClick(); view.render()
        const res = {}
        press('card-editor', { nativeEvent: { isComposing: true }, keyCode: 229 }); res.composing = count('card-editor')
        press('card-editor', { nativeEvent: { isComposing: false }, keyCode: 229 }); res.code229 = count('card-editor')
        press('card-editor', { nativeEvent: { isComposing: false }, keyCode: 27 }); res.plain = count('card-editor')
        button(view.tree, /^New deck$/).props.onClick(); view.render()
        press('new-deck', { nativeEvent: { isComposing: true }, keyCode: 229 }); res.formComposing = count('new-deck')
        press('new-deck', { nativeEvent: { isComposing: false }, keyCode: 27 }); res.formPlain = count('new-deck')
        console.log(JSON.stringify(res))
    """)
    assert out == {"composing": 1, "code229": 1, "plain": 0, "formComposing": 1, "formPlain": 0}, out


# ---- P2-UI-03, P2-UI-08: what the bar says after an import, and after its Undo ----------------------------

IMPORT = EDITOR + """
const pick = async name => {
  field('Deck file').props.onChange({ target: { files: [{ name, size: 40, text: async () => 'deck: x' }], value: 'x' } })
  await view.settle()
}
const bar = () => text(all(view.tree, n => n.props['data-ubk'] === 'undo'))
const undo = async () => { button(view.tree, /^Undo$/).props.onClick(); await view.settle(); return bar() }
"""


def test_import_note_and_undo_follow_replaced_and_the_undo_kind(tmp_path):
    """P2-UI-03: a fresh import (`replaced: false`, undo {delete}) reads "Imported", and its Undo says the
    deck is removed (not "removed again"); a replace (`replaced: true`, undo {restore}) reads "Replaced"
    and its Undo brings the old version back. P2-UI-08: the notes name the deck, not its file name."""
    out = run_js(tmp_path, IMPORT + """
        setAnswer((m, p, b) => {
          if (p === '/decks/import' && b.file_name === 'fresh-one.yaml') return { ok: true, schema: 1, deck: 'fresh-one', source: 'imported', cards: 3, version: 1, replaced: false, undo: { delete: 'fresh-one' }, note: 'Off for auto-draw.' }
          if (p === '/decks/import' && !b.replace) return { __status: 409, body: { ok: false, schema: 1, error: 'exists', message: 'you already have a deck mine' } }
          if (p === '/decks/import') return { ok: true, schema: 1, deck: 'mine', source: 'imported', cards: 1, version: 3, replaced: true, undo: { restore: 2 } }
          if (p === '/decks/mine/restore') return { ok: true, schema: 1, deck: 'mine', restored: 2, version: 4, summary: 'back' }
          if (p === '/decks/fresh-one/delete') return { ok: true, schema: 1, deck: 'fresh-one', version: 2, summary: 'deleted', undo: { restore: 2 } }
          return { ok: true, schema: 1 }
        })
        const res = {}
        await pick('fresh-one.yaml'); res.fresh = bar(); res.freshUndo = await undo()
        await pick('mine.yaml')
        const dialog = all(view.render(), n => n.type === 'ConfirmDialog' && /Replace/.test(n.props.title || ''))[0]
        button(view.tree, /^Replace mine$/).props.onClick(); view.render()
        await all(view.tree, n => n.type === 'ConfirmDialog' && n.props.open && /Replace/.test(n.props.title || ''))[0].props.onConfirm()
        await view.settle()
        res.replaced = bar(); res.replacedUndo = await undo()
        res.sent = posts().map(([m, p]) => p)
        console.log(JSON.stringify(res))
    """)
    assert out["fresh"].startswith("Imported fresh-one (3 cards)"), out["fresh"]
    assert "Undone: fresh-one is removed." in out["freshUndo"] and "again" not in out["freshUndo"], out["freshUndo"]
    assert out["replaced"].startswith("Replaced Mine (1 cards)"), out["replaced"]
    assert "Undone: Mine is back at version 2." in out["replacedUndo"], out["replacedUndo"]
    assert "/decks/fresh-one/delete" in out["sent"] and "/decks/mine/restore" in out["sent"]


def test_notes_after_a_save_and_a_delete_name_the_deck(tmp_path):
    """P2-UI-08: "Saved", "Deleted" and "Undone" name the deck ("Mine"), not its file name, also after
    the deck has left the list."""
    out = run_js(tmp_path, EDITOR + """
        setAnswer((m, p) => {
          if (p === '/decks/mine/preview') return { ok: true, schema: 1, target: 'mine', summary: '1 card removed', cards: 0, confirm: 'c1', diff: {} }
          if (m === 'PUT' && p === '/decks/mine') return { ok: true, schema: 1, deck: 'mine', version: 3, summary: '1 card removed', undo: { restore: 2 } }
          if (p === '/decks/mine/restore') return { ok: true, schema: 1, deck: 'mine', restored: 2, version: 4, summary: 'back' }
          if (p === '/decks/mine/delete') return { ok: true, schema: 1, deck: 'mine', version: 5, summary: 'deleted', undo: { restore: 5 } }
          return { ok: true, schema: 1 }
        })
        const bar = () => text(all(view.tree, n => n.props['data-ubk'] === 'undo'))
        one(all(view.tree, n => n.type === 'button' && n.props.className === 'nm' && text(n) === 'Mine'), 'Mine').props.onClick()
        view.render()
        all(view.tree, n => n.props['aria-label'] === 'Remove mi-01')[0].props.onClick(); await view.settle()
        await view.settle(20)
        button(view.tree, /^Save$/).props.onClick(); await view.settle(20)
        const res = { saved: bar() }
        button(view.tree, /^Undo$/).props.onClick(); await view.settle()
        res.undone = bar()
        button(view.tree, /^Delete deck$/).props.onClick(); view.render()
        await all(view.tree, n => n.type === 'ConfirmDialog' && n.props.open)[0].props.onConfirm()
        await view.settle()
        res.deleted = bar()
        console.log(JSON.stringify(res))
    """)
    assert out["saved"].startswith("Saved Mine: 1 card removed (version 3)."), out["saved"]
    assert out["undone"].startswith("Undone: Mine is back at version 2."), out["undone"]
    assert out["deleted"].startswith("Deleted Mine."), out["deleted"]


# ---- P2-UI-01: New deck never takes a shipped deck's file names --------------------------------------

def test_new_deck_refuses_shipped_and_own_copy_file_names(tmp_path):
    """P2-UI-01: "Coding own" (file name coding-own) would take the place of the shipped Coding; any slug
    of a shipped or community deck, and that deck's "-own" file name, is refused with a line that says to
    edit that deck instead. An own deck's "-own" name is fine."""
    out = run_js(tmp_path, """
        import { newDeckProblem } from '@src/decks.js'
        import { DECKS } from './data.js'
        const decks = [...DECKS.decks, { deck: 'poetry', name: 'Poetry', source: 'community', cards: 5, switch: { draw: true, auto: false } },
          { deck: 'design', name: 'Design', source: 'shipped', cards: 6, switch: { draw: true, auto: false }, shadowed_by: 'design' }]
        const p = (name, slug) => newDeckProblem(name, slug, decks)
        console.log(JSON.stringify({ codingOwn: p('Coding own', 'coding-own'), writingOwn: p('Writing own', 'writing-own'),
          poetryOwn: p('Verses', 'poetry-own'), poetry: p('Verses', 'poetry'), designOwn: p('Design own', 'design-own'),
          mineOwn: p('Mine own', 'mine-own'), zebra: p('Zebra cards', 'zebra-cards') }))
    """)
    for k in ("codingOwn", "writingOwn", "poetryOwn", "poetry", "designOwn"):
        assert out[k], k
        assert "edit" in out[k].lower(), out[k]
        assert len(out[k]) <= 160, out[k]
    assert "Coding" in out["codingOwn"] and "Writing" in out["writingOwn"] and "Poetry" in out["poetryOwn"]
    assert out["mineOwn"] == "" and out["zebra"] == ""


# ---- P2-UI-04: a failed "Replace mine" -----------------------------------------------------------------

def test_a_failed_replace_rejects_so_the_dialog_shows_the_error(tmp_path):
    """P2-UI-04: when the replace fails, the confirm's onConfirm rejects with the plain sentence, so
    Desktop's ConfirmDialog shows it inline and plays no "Done" beat; the import box says it too."""
    out = run_js(tmp_path, IMPORT + """
        setAnswer((m, p, b) => {
          if (p === '/decks/import' && !b.replace) return { __status: 409, body: { ok: false, schema: 1, error: 'exists', message: 'you already have a deck mine' } }
          if (p === '/decks/import') return { __status: 500, body: { ok: false, schema: 1, error: 'internal', message: 'the plugin hit an unexpected error' } }
          return { ok: true, schema: 1 }
        })
        await pick('mine.yaml')
        button(view.tree, /^Replace mine$/).props.onClick(); view.render()
        const dialog = all(view.tree, n => n.type === 'ConfirmDialog' && n.props.open && /Replace/.test(n.props.title || ''))[0]
        let rejected = null
        await dialog.props.onConfirm().then(() => { rejected = false }, e => { rejected = e.message })
        await view.settle()
        console.log(JSON.stringify({ rejected, box: text(all(view.tree, n => n.props['data-ubk'] === 'import')) }))
    """)
    assert out["rejected"] == "the plugin hit an unexpected error", out
    assert "the plugin hit an unexpected error" in out["box"]


# ---- P2-UI-07: a host refusal the user can act on ----------------------------------------------------

def test_host_401_and_413_keep_a_hint_in_the_plain_sentence(tmp_path):
    """P2-UI-07: a 401 from the host says the user is not signed in to Hermes, a 413 says the file is too
    large; a short host `detail` is kept; raw server text and FastAPI's detail lists still never show."""
    out = run_js(tmp_path, """
        import { restError } from '@src/core.js'
        const m = e => restError(new Error(e)).message
        console.log(JSON.stringify({
          a401: m('401: ' + JSON.stringify({ detail: 'Not authenticated' })),
          a413: m('413: Request Entity Too Large'),
          a403: m('403: ' + JSON.stringify({ detail: 'Forbidden by policy' })),
          raw500: m('500: Internal Server Error'),
          d500: m('500: ' + JSON.stringify({ detail: 'Internal Server Error' })),
          list422: m('422: ' + JSON.stringify({ detail: [{ type: 'int_parsing', msg: 'bad' }] })),
        }))
    """)
    assert "Not signed in to Hermes" in out["a401"], out["a401"]
    assert "File too large" in out["a413"], out["a413"]
    assert "Forbidden by policy" in out["a403"], out["a403"]
    for k in ("raw500", "d500", "list422"):
        assert "Internal Server Error" not in out[k] and "int_parsing" not in out[k], out[k]
        assert "try again" in out[k].lower()
    for v in out.values():
        assert len(v) <= 160, v


# ---- P2-UI-10: the shortcut never trusts an old deck list --------------------------------------------

def test_shortcut_rereads_a_stale_deck_list_before_trusting_it(tmp_path):
    """P2-UI-10: a cached deck list older than 30 s is read again before the shortcut sends a deck by
    name; a fresh one is used as it is (no extra GET per press)."""
    out = run_js(tmp_path, """
        import plugin from '@src/index.js'
        import { fakeCtx, setAnswer, rests, queryClient } from './helpers.js'
        import { DECKS, SETTINGS, CARD, K } from './data.js'
        let server = DECKS
        setAnswer((m, p) => {
          if (m === 'GET' && p === '/decks') return server
          if (m === 'GET' && p === '/settings') return SETTINGS
          if (m === 'POST' && p === '/draw') return { ok: true, schema: 1, card: CARD, draw_id: 'd-' + rests.length }
          return { ok: true, schema: 1 }
        })
        const ctx = fakeCtx()
        plugin.register(ctx)
        await new Promise(r => setTimeout(r, 20))
        const key = ctx.reg.find(c => c.id === 'draw-key').data
        const press = async () => {
          ctx.storage.set('deck:test', 'writing')
          const n = rests.length
          await key.run()
          await new Promise(r => setTimeout(r, 5))
          const sent = rests.slice(n)
          return { draws: sent.filter(([m, p]) => p === '/draw').map(r => r[2].deck || null), gets: sent.filter(([m, p]) => m === 'GET' && p === '/decks').length }
        }
        queryClient.setQueryData(K('decks'), DECKS)
        const fresh = await press()
        server = { ...DECKS, decks: DECKS.decks.map(d => (d.deck === 'writing' ? { ...d, switch: { draw: false, auto: false } } : d)) }
        queryClient.age(K('decks'), 120000)
        const stale = await press()
        console.log(JSON.stringify({ fresh, stale }))
    """)
    assert out["fresh"] == {"draws": ["writing"], "gets": 0}, out
    assert out["stale"] == {"draws": [None], "gets": 1}, out


# ---- P2-UI-09: user text takes its direction from the text --------------------------------------------

def test_deck_names_and_diff_lines_carry_dir_auto(tmp_path):
    """P2-UI-09: the diff list's card lines, the sheet header, the deck list, the settings switch table
    and the table's deck chooser set dir="auto" on deck and card text."""
    out = run_js(tmp_path, EDITOR + """
        import { SettingsPage } from '@src/settings.js'
        import { TableView } from '@src/table.js'
        const name = 'دفتر'
        const decks = { ...DECKS, decks: DECKS.decks.map(d => (d.deck === 'mine' ? { ...d, name } : d)) }
        queryClient.setQueryData(K('deck', 'mine'), { ...MINE, deck: { ...MINE.deck, name } })
        queryClient.setQueryData(K('decks'), decks)
        queryClient.setQueryData(K('settings'), { ok: true, schema: 1, settings: { autodraw: false, autodraw_decks: [] } })
        setAnswer(() => ({ ok: true, schema: 1, target: 'mine', summary: '1 card', cards: 2, confirm: 'c1',
          diff: { added: [{ id: 'mi-02', human: 'اقرأ' }], removed: [{ id: 'mi-01', human: 'קרא' }], changed: [{ id: 'mi-03', fields: ['human'], before: { human: 'a' }, after: { human: 'ب' } }] } }))
        const v = mount(jsx(DecksView, { decksData: decks }))
        one(all(v.tree, n => n.type === 'button' && n.props.className === 'nm' && text(n) === name), name).props.onClick()
        v.render()
        v.render(); all(v.tree, n => n.props['aria-label'] === 'Remove mi-01')[0].props.onClick(); await v.settle(); await v.settle()
        // The innermost element whose own text is the user text.
        const holders = (tree, s) => all(tree, n => typeof n.props.children === 'string' ? n.props.children.includes(s)
          : Array.isArray(n.props.children) && n.props.children.some(c => typeof c === 'string' && c.includes(s)))
        const dirOf = (tree, s) => holders(tree, s).map(n => n.props.dir || null)
        const head = all(v.tree, n => n.type === 'h2').filter(n => text(n).includes(name))
        const diff = all(v.tree, n => n.type === 'ul' && n.props.className === 'difflist')[0]
        const res = {
          head: head.map(n => [n.props.dir || null, ...dirOf(n, name)].some(d => d === 'auto')),
          list: dirOf(all(v.tree, n => n.props['data-ubk'] === 'decklist')[0], name),
          diff: ['mi-02: اقرأ', 'mi-01: קרא', 'ب'].map(s => dirOf(diff, s)),
          settings: dirOf(all(mount(jsx(SettingsPage, {})).tree, n => n.props['data-ubk'] === 'switches')[0], name),
          table: dirOf(mount(jsx(TableView, { decks: decks.decks })).tree, name),
        }
        console.log(JSON.stringify(res))
    """)
    assert out["head"] == [True], out
    assert out["list"] == ["auto"], out
    assert out["settings"] == ["auto"], out
    assert out["table"] == ["auto"], out
    for d in out["diff"]:
        assert d and all(x == "auto" for x in d), out["diff"]


# ---- P2-UI-02: one count of problems on one screen ----------------------------------------------------

def test_a_refusal_with_problems_says_how_many_once_above_the_list(tmp_path):
    """P2-UI-02: when a 422 carries `problems`, the line above the list is a short count ("The deck breaks
    1600 rules:"), not the backend message that repeats the first problems with its own remainder. The
    preview panel does the same. A refusal without problems still shows its message."""
    out = run_js(tmp_path, IMPORT + """
        const probs = n => Array.from({ length: n }, (_, i) => ({ card: `bg-${i}`, rule: 'tags', message: 'unknown tag nope' }))
        const long = 'The deck breaks these rules: ' + probs(6).map(p => `${p.card}: ${p.message} (${p.rule})`).join('; ') + ' and 1594 more'
        let mode = 'many'
        setAnswer((m, p) => {
          if (p === '/decks/import' && mode === 'many') return { __status: 422, body: { ok: false, schema: 1, error: 'invalid_deck', message: long, problems: probs(50), problems_more: 1550 } }
          if (p === '/decks/import' && mode === 'one') return { __status: 422, body: { ok: false, schema: 1, error: 'invalid_deck', message: 'The deck breaks these rules: bg-0: unknown tag', problems: probs(1) } }
          if (p === '/decks/import') return { __status: 400, body: { ok: false, schema: 1, error: 'invalid', message: 'the file is not a deck' } }
          if (p === '/decks/mine/preview') return { __status: 422, body: { ok: false, schema: 1, error: 'invalid_deck', message: long, problems: probs(50), problems_more: 71 } }
          return { ok: true, schema: 1 }
        })
        const alertIn = id => text(all(all(view.tree, n => n.props['data-ubk'] === id)[0], n => n.props.role === 'alert'))
        const res = {}
        await pick('big.yaml'); res.many = alertIn('import')
        mode = 'one'; await pick('one.yaml'); res.one = alertIn('import')
        mode = 'none'; await pick('odd.yaml'); res.none = alertIn('import')
        one(all(view.tree, n => n.type === 'button' && n.props.className === 'nm' && text(n) === 'Mine'), 'Mine').props.onClick()
        view.render()
        all(view.tree, n => n.props['aria-label'] === 'Remove mi-01')[0].props.onClick(); await view.settle(); await view.settle()
        res.preview = alertIn('preview')
        console.log(JSON.stringify(res))
    """)
    assert out["many"] == "The deck breaks 1600 rules:", out
    assert out["one"] == "The deck breaks one rule:", out
    assert out["none"] == "the file is not a deck", out
    assert out["preview"] == "The deck breaks 121 rules:", out
