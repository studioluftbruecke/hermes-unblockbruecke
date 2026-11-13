// The Decks tab: the library with one Draw switch per deck (the switch for Hermes
// is on the Hermes tab), the selected deck's cards with what the journal says about them, and the
// editor. Your own decks save at once (one PUT per edit) with Undo and no Preview; a shipped deck
// has one "Make my own copy", which still goes preview -> diff -> Save, like an import. Tags are
// optional in your own decks; the file name is never asked for. Row actions show on hover or focus.
import { ConfirmDialog, Switch } from '@hermes/plugin-sdk'
import { useEffect, useRef, useState } from 'react'
import { jsx } from 'react/jsx-runtime'

import { api } from './api.js'
import { BUILTIN_TAGS, charCount, SLUG_RE, TAG_RE, toast, whenLocal } from './core.js'
import { refreshPalette } from './palette.js'
import { invalidateDecks, useDeck, useVersions, visibleDecks } from './queries.js'
import { setPressed, storedPressed } from './state.js'
import { Btn, h, hk, Mark, SOURCE_LABEL } from './ui.js'

const parseTags = text => String(text || '').split(/[\s,]+/).map(t => t.trim().toLowerCase()).filter(Boolean)
const slugOf = name => String(name || '').toLowerCase().normalize('NFKD').replace(/[\u0300-\u036f]/g, '').replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 40)

function afterWrite() {
  invalidateDecks()
  refreshPalette()
}

/** Escape works as Cancel in every editing panel (the inner one handles it first). An Escape that
 *  ends an IME composition (dropping a candidate) belongs to the input method and cancels nothing. */
const escapeCancels = onCancel => e => {
  if (e.key !== 'Escape' || e.defaultPrevented) return
  if ((e.nativeEvent && e.nativeEvent.isComposing) || e.isComposing || e.keyCode === 229) return
  e.preventDefault()
  e.stopPropagation()
  onCancel()
}

// A refusal can list thousands of problems; the backend caps the list and says how many it left out
// (problems_more). Show at most this many either way.
const PROBLEMS_SHOWN = 50
const problemsOf = body => (body && Array.isArray(body.problems) ? { list: body.problems, more: Number(body.problems_more) || 0 } : null)
/** The line above a refusal: a count when the answer lists problems (the list below names them, and
 *  the backend message would repeat the first few with a remainder of its own), else the message. */
const refusalText = error => {
  const p = problemsOf(error.body)
  if (!p || !p.list.length) return error.message
  const n = p.list.length + p.more
  return n === 1 ? 'The deck breaks one rule:' : `The deck breaks ${n} rules:`
}

function ProblemList({ problems }) {
  const shown = problems.list.slice(0, PROBLEMS_SHOWN)
  const rest = problems.list.length - shown.length + problems.more
  return h('div', { className: 'col', style: { gap: 4 } },
    h('ul', { className: 'problems', 'data-ubk': 'problems' }, shown.map((p, i) => jsx('li', { dir: 'auto', children: `${p.card ? `${p.card}: ` : ''}${p.message} (rule ${p.rule})` }, i))),
    rest > 0 ? h('p', { className: 'note' }, `and ${rest} more`) : null)
}

// ---- the undo bar ------------------------------------------------------------------------------

/** A note's text is a string, or a function of `nameOf` (slug -> deck name) so a deck that only
 *  shows up in the list after the write still gets its name once the list reloads. */
const noteText = (note, nameOf) => (typeof note.text === 'function' ? note.text(nameOf) : note.text)

function UndoBar({ note, onClose, nameOf }) {
  useEffect(() => {
    const t = setTimeout(onClose, 12000)
    return () => clearTimeout(t)
  }, [note])
  if (!note) return null
  return h('div', { className: 'toastbar', role: 'status', 'data-ubk': 'undo' },
    h('span', { className: 'grow', dir: 'auto' }, noteText(note, nameOf)),
    note.undo ? h(Btn, { sm: true, onClick: async () => { onClose(); await note.undo() } }, 'Undo') : null,
    h('button', { type: 'button', className: 'link', onClick: onClose }, 'Dismiss'))
}

/** Turn a save/restore/delete answer's `undo` into a function. */
function undoFor(slug, undo, done) {
  if (!undo) return null
  if (undo.restore !== undefined) return async () => {
    try {
      const out = await api.restore(slug, undo.restore)
      afterWrite()
      done(n => `Undone: ${n(slug)} is back at version ${out.restored}.`)
    } catch (error) {
      toast(`Could not undo: ${error.message}`, 'warning')
    }
  }
  if (undo.delete) return async () => {
    try {
      await api.remove(undo.delete)
      afterWrite()
      done(n => `Undone: ${n(undo.delete)} is removed.`)
    } catch (error) {
      toast(`Could not undo: ${error.message}`, 'warning')
    }
  }
  return null
}

// ---- the preview panel -------------------------------------------------------------------------

function DiffList({ diff }) {
  const rows = []
  for (const c of diff.added || []) rows.push(['added', h('span', { dir: 'auto' }, `${c.id}: ${c.human}`)])
  for (const c of diff.removed || []) rows.push(['removed', h('del', { dir: 'auto' }, `${c.id}: ${c.human}`)])
  for (const c of diff.changed || []) for (const f of c.fields || []) {
    const show = v => (Array.isArray(v) ? v.join(', ') : String(v ?? ''))
    rows.push([`${c.id} ${f}`, h('span', null, h('del', { dir: 'auto' }, show(c.before && c.before[f])), ' ', h('ins', { dir: 'auto' }, show(c.after && c.after[f])))])
  }
  if (diff.meta && diff.meta.length) rows.push(['deck', `changed ${diff.meta.join(', ')}`])
  if (!rows.length) return null
  return h('ul', { className: 'difflist' }, rows.map(([k, v], i) => jsx('li', { children: [jsx('span', { className: 'k', children: k }, 'k'), jsx('span', { children: v }, 'v')] }, i)))
}

/** Preview a change (POST /decks/{slug}/preview), then Save it (PUT with confirm). A 409 stale_preview
 *  shows the fresh preview from the answer; a 422 lists the rules the deck would break. */
function PreviewPanel({ slug, change, onCancel, onSaved }) {
  const [pv, setPv] = useState(null)
  const [problems, setProblems] = useState(null)
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    let live = true
    setPv(null)
    setProblems(null)
    setMessage('')
    api.preview(slug, change.body).then(out => live && setPv(out)).catch(error => {
      if (!live) return
      setProblems(problemsOf(error.body))
      setMessage(refusalText(error))
    })
    return () => {
      live = false
    }
  }, [slug, change])
  const save = async () => {
    if (!pv) return
    setBusy(true)
    try {
      const out = await api.save(slug, { ...change.body, confirm: pv.confirm })
      afterWrite()
      onSaved(out)
    } catch (error) {
      if (error.code === 'stale_preview' && error.body && error.body.preview) {
        setPv(error.body.preview)
        setMessage('The deck changed since that preview. This is the fresh one; check it and save again.')
      } else {
        setProblems(problemsOf(error.body))
        setMessage(refusalText(error))
      }
    } finally {
      setBusy(false)
    }
  }
  const bad = !!problems
  return h('div', { className: `preview${bad ? ' bad' : ''}`, 'data-ubk': 'preview', onKeyDown: escapeCancels(onCancel) },
    h('div', { className: 'row' }, h('strong', { className: 'grow' }, `Preview: ${change.label}`),
      pv && pv.copy_of ? h('span', { className: 'badge own' }, `saves as your copy ${pv.target}`) : null),
    !pv && !message ? h('p', { className: 'note' }, 'Checking the change…') : null,
    pv ? h('p', null, h('span', { className: 'muted' }, 'What changes: '), pv.summary || (pv.diff && pv.diff.summary)) : null,
    pv && pv.diff ? h(DiffList, { diff: pv.diff }) : null,
    message ? h('p', { className: bad ? 'note' : 'note', role: bad ? 'alert' : undefined }, message) : null,
    problems ? h(ProblemList, { problems }) : null,
    h('div', { className: 'row' },
      h(Btn, { pri: true, onClick: save, disabled: !pv || busy || bad }, busy ? 'Saving…' : 'Save'),
      h(Btn, { onClick: onCancel }, 'Cancel'),
      pv ? h('span', { className: 'note' }, `${pv.cards} cards after the change; the old version stays under Versions.`) : null))
}

// ---- the cards table ---------------------------------------------------------------------------

function CardEditor({ initial, onPreview, onCancel, submitLabel = 'Save', blocked = false }) {
  const [human, setHuman] = useState(initial.human || '')
  const [agent, setAgent] = useState(initial.agent || '')
  const [tags, setTags] = useState((initial.tags || []).join(', '))
  const tagList = parseTags(tags)
  const badTag = tagList.find(t => !TAG_RE.test(t))
  // Characters as the backend counts them (code points): an emoji is one, not two.
  const hn = charCount(human)
  const an = charCount(agent)
  const ok = human.trim() && agent.trim() && hn <= 90 && an <= 220 && !badTag && tagList.length <= 4 && !blocked
  return h('div', { className: 'col', 'data-ubk': 'card-editor', onKeyDown: escapeCancels(onCancel) },
    h('label', { className: 'col', style: { gap: 3 } }, h('span', { className: 'note' }, `Human face (${hn}/90)`),
      h('textarea', { className: 'inp', rows: 2, value: human, dir: 'auto', onChange: e => setHuman(e.target.value.replace(/\n/g, ' ')), 'aria-label': 'Human face' })),
    h('label', { className: 'col', style: { gap: 3 } }, h('span', { className: 'note' }, `Agent face (${an}/220)`),
      h('textarea', { className: 'inp', rows: 3, value: agent, dir: 'auto', onChange: e => setAgent(e.target.value.replace(/\n/g, ' ')), 'aria-label': 'Agent face' })),
    h('label', { className: 'col', style: { gap: 3 } }, h('span', { className: 'note' }, 'Tags, if you like (up to 4, comma separated)'),
      h('input', { className: 'inp', value: tags, onChange: e => setTags(e.target.value), 'aria-label': 'Tags' })),
    badTag ? h('p', { className: 'note' }, `"${badTag}" is not a tag: lowercase letters, digits and "-", 2 to 21 characters.`) : null,
    h('div', { className: 'row' },
      h(Btn, { pri: true, disabled: !ok, onClick: () => onPreview({ human: human.trim(), agent: agent.trim(), tags: tagList.length ? tagList : undefined }) }, submitLabel),
      h(Btn, { onClick: onCancel }, 'Cancel')))
}

/** A tag's meaning, shown on hover: the deck's glossary, else the built-in line. */
const tagMeaning = (deck, tag) => (deck.glossary && deck.glossary[tag]) || BUILTIN_TAGS[tag] || ''

function CardsTable({ deck, onChange, editing, setEditing, editable }) {
  const cards = deck.cards || []
  return h('div', { className: 'scroll' }, h('table', { className: 'tbl', 'data-ubk': 'cards' },
    h('thead', null, h('tr', null, h('th', null, 'Card'), h('th', null, 'Human face'), h('th', null, 'Agent face'), h('th', null, 'Tags'),
      h('th', { className: 'num' }, 'Drawn'), h('th', { className: 'num' }, 'Helped'), h('th', null, ''))),
    h('tbody', null, cards.map(c => {
      const stats = c.stats || {}
      if (editing === c.id) {
        return jsx('tr', { className: 'editing', children: [jsx('td', { className: 'id', children: c.id }, 'i'),
          jsx('td', { colSpan: 6, children: h(CardEditor, { initial: c, onCancel: () => setEditing(null),
            onPreview: v => onChange({ label: `edit ${c.id}`, body: { changes: { edit: [{ id: c.id, ...v, tags: v.tags || [] }] } } }) }) }, 'e')] }, c.id)
      }
      return jsx('tr', { children: [
        jsx('td', { className: 'id', children: c.id }, 'i'),
        jsx('td', { className: 'hf', dir: 'auto', children: c.human }, 'h'),
        jsx('td', { className: 'af', dir: 'auto', children: c.agent }, 'a'),
        jsx('td', { children: h('span', { className: 'tags' }, (c.tags || []).map(t => jsx('span', { title: tagMeaning(deck, t) || undefined, children: t }, t))) }, 't'),
        jsx('td', { className: 'num', children: String(stats.drawn ?? 0) }, 'd'),
        jsx('td', { className: 'num', children: String(stats.helped ?? 0) }, 'p'),
        jsx('td', { className: 'rowacts', children: editable ? h('span', { className: 'row', style: { flexWrap: 'nowrap', gap: 10 } },
          h(Btn, { text: true, onClick: () => setEditing(c.id), 'aria-label': `Edit ${c.id}` }, 'Edit'),
          h(Btn, { text: true, onClick: () => onChange({ label: `remove ${c.id}`, body: { changes: { remove: [c.id] } } }), 'aria-label': `Remove ${c.id}` }, 'Remove')) : null }, 'x'),
      ] }, c.id)
    }))))
}

// ---- versions, export --------------------------------------------------------------------------

function Versions({ slug, onRestored }) {
  const q = useVersions(slug)
  const list = (q.data && q.data.versions) || []
  if (q.isLoading) return h('p', { className: 'note' }, 'Loading versions…')
  if (q.error) return h('p', { className: 'note' }, q.error.code === 'unknown_deck' ? 'No saved versions yet.' : `The versions did not load: ${q.error.message}`)
  if (!list.length) return h('p', { className: 'note' }, 'No saved versions yet. Shipped decks are versioned by the plugin; your edits start your own copy.')
  return h('table', { className: 'tbl', 'data-ubk': 'versions' }, h('tbody', null, list.map((v, i) => jsx('tr', { children: [
    jsx('td', { className: 'id', children: `#${v.n}` }, 'n'),
    jsx('td', { className: 'id', children: whenLocal(v.at) }, 'a'),
    jsx('td', { children: v.author === 'agent' ? 'Hermes' : 'you' }, 'w'),
    jsx('td', { children: `${v.summary}${v.deleted ? ' (deleted)' : ''}` }, 's'),
    jsx('td', { children: i === 0 ? h('span', { className: 'note' }, 'current') : h(Btn, { sm: true, onClick: async () => {
      try {
        const out = await api.restore(slug, v.n)
        afterWrite()
        onRestored(out)
      } catch (error) {
        toast(`Could not restore: ${error.message}`, 'warning')
      }
    } }, 'Restore') }, 'r'),
  ] }, v.n))))
}

async function exportDeck(slug) {
  try {
    const out = await api.exportDeck(slug)
    const url = URL.createObjectURL(new Blob([out.yaml], { type: 'application/yaml' }))
    const a = document.createElement('a')
    a.href = url
    a.download = out.file_name || `${slug}.yaml`
    document.body.appendChild(a)
    a.click()
    a.remove()
    setTimeout(() => URL.revokeObjectURL(url), 4000)
    toast(`Saved ${a.download} to your downloads.`)
  } catch (error) {
    toast(`Could not export: ${error.message}`, 'warning')
  }
}

// ---- import, new deck --------------------------------------------------------------------------

/** A file name no deck uses yet, from `base`: base, base-2, base-3, ... (the user never types one). */
export function freeSlug(base, decks) {
  const taken = new Set((decks || []).map(d => d.deck))
  const root = (SLUG_RE.test(base) ? base : 'my-deck').slice(0, 36).replace(/-+$/, '') || 'my-deck'
  if (!taken.has(root)) return root
  for (let i = 2; i < 100; i++) if (!taken.has(`${root}-${i}`)) return `${root}-${i}`
  return `${root}-${Date.now().toString(36).slice(-3)}`
}

function ImportBox({ decks, onImported }) {
  const input = useRef(null)
  const [state, setState] = useState(null) // {yaml, file_name, error, exists, problems, slug}
  const [confirmReplace, setConfirmReplace] = useState(false)
  // From the replace confirm, a failure is thrown on as well: Desktop's ConfirmDialog then shows it in
  // the dialog and plays no "Done" beat for a replace that did not happen.
  const send = async (extra = {}, { rethrow = false } = {}) => {
    const body = { yaml: state.yaml, file_name: state.file_name, ...extra }
    try {
      const out = await api.importDeck(body)
      afterWrite()
      setState(null)
      onImported(out)
    } catch (error) {
      setState({ ...state, ...extra, error: refusalText(error), code: error.code, exists: error.code === 'exists' || (!!extra.replace && !!state.exists), problems: problemsOf(error.body) })
      if (rethrow) throw error
    }
  }
  const pick = async e => {
    const file = e.target.files && e.target.files[0]
    e.target.value = ''
    if (!file) return
    if (file.size > 256 * 1024) {
      setState({ error: 'That file is larger than 256 KB; a deck file is much smaller.' })
      return
    }
    const yaml = await file.text()
    const next = { yaml, file_name: file.name, slug: slugOf(file.name.replace(/\.(ya?ml)$/i, '')) }
    setState(next)
    try {
      const out = await api.importDeck({ yaml, file_name: file.name })
      afterWrite()
      setState(null)
      onImported(out)
    } catch (error) {
      setState({ ...next, error: refusalText(error), code: error.code, exists: error.code === 'exists', problems: problemsOf(error.body) })
    }
  }
  return h('div', { className: 'col', 'data-ubk': 'import' },
    h('div', { className: 'row' },
      h(Btn, { sm: true, onClick: () => input.current && input.current.click() }, 'Import a deck file'),
      h('input', { ref: input, type: 'file', accept: '.yaml,.yml,text/yaml,application/yaml', style: { display: 'none' }, onChange: pick, 'aria-label': 'Deck file' })),
    state && state.error ? h('p', { className: 'note', role: 'alert' }, state.code === 'exists' ? 'You already have a deck from a file of that name.' : state.error) : null,
    state && state.problems ? h(ProblemList, { problems: state.problems }) : null,
    state && state.exists ? h('div', { className: 'row' },
      h(Btn, { sm: true, onClick: () => send({ slug: freeSlug(state.slug, decks) }) }, 'Import as a new deck'),
      h(Btn, { sm: true, danger: true, onClick: () => setConfirmReplace(true) }, 'Replace mine')) : null,
    jsx(ConfirmDialog, { open: confirmReplace, onClose: () => setConfirmReplace(false), destructive: true, title: 'Replace your deck with this file?',
      description: 'The file takes the place of your deck of the same name. Your version stays under Versions, and Undo brings it back.',
      confirmLabel: 'Replace mine', onConfirm: () => send({ replace: true }, { rethrow: true }) }))
}

/** Why a new deck cannot take this name, or '' when it can. The file name is made from the name and
 *  never shown, so every refusal speaks about the name. */
export function newDeckProblem(name, slug, decks) {
  const n = name.trim()
  if (!n) return 'Give the deck a name.'
  if (charCount(n) > 40) return 'The name can have at most 40 characters.'
  if (!SLUG_RE.test(slug)) return 'The name needs at least two letters or digits.'
  const list = decks || []
  const named = list.find(d => String(d.name || '').trim().toLowerCase() === n.toLowerCase())
  if (named) {
    return named.source === 'shipped' || named.source === 'community'
      ? `${named.name} comes with the plugin. Open it and make your own copy instead.`
      : `A deck named ${named.name} is already there. Pick another name.`
  }
  return ''
}

/** A file name for a new deck called `name`: made from the name, never one that holds a shipped
 *  deck's own copy (`<slug>-own`), and never one already taken. */
export const newDeckSlug = (name, decks) => {
  const base = slugOf(name)
  const bundled = (decks || []).some(d => (d.source === 'shipped' || d.source === 'community') && (d.deck === base || `${d.deck}-own` === base))
  return freeSlug(bundled ? `${base}-deck` : base, decks)
}

function NewDeck({ decks, onCancel, onSave }) {
  const [name, setName] = useState('')
  const slug = newDeckSlug(name, decks)
  const problem = newDeckProblem(name, slug, decks)
  return h('div', { className: 'panel col', style: { padding: 14 }, 'data-ubk': 'new-deck', onKeyDown: escapeCancels(onCancel) },
    h('h2', null, 'New deck'),
    h('label', { className: 'col', style: { gap: 3 } }, h('span', { className: 'note' }, 'Name'), h('input', { className: 'inp', value: name, dir: 'auto', onChange: e => setName(e.target.value), 'aria-label': 'Deck name' })),
    // Always in the tree, empty when the name is fine: a line that came and went would shift the card
    // editor below it to another child position, and React would remount it with an empty draft.
    h('p', { className: 'note', role: 'alert', 'data-ubk': 'new-deck-problem', style: { color: 'var(--ubk-red)', minHeight: '1.4em' } }, name.trim() ? problem : ''),
    h('p', { className: 'note' }, 'Write its first card; you can add more after saving.'),
    h(CardEditor, { initial: { tags: [] }, onCancel, submitLabel: 'Save the new deck', blocked: !!problem,
      onPreview: v => !problem && onSave(slug, { label: `new deck ${name.trim()}`, body: { changes: { meta: { name: name.trim() }, add: [v] } } }) }))
}

/** Save an edit of your own deck at once: one PUT without a preview. A backend that still wants
 *  the preview's confirm value (0.1) or refuses the change answers with an error; the caller then
 *  shows the preview panel, which explains the refusal or saves the 0.1 way. */
async function saveAtOnce(slug, change) {
  try {
    const out = await api.save(slug, change.body)
    afterWrite()
    return { out }
  } catch (error) {
    return { error }
  }
}

const savedNote = (out, setNote) => ({ text: n => `Saved ${n(out.deck)}: ${out.summary}${out.version ? ` (version ${out.version})` : ''}.`, undo: undoFor(out.deck, out.undo, text => setNote({ text })) })

// ---- the sheet -----------------------------------------------------------------------------------

const isOwn = deck => deck.source === 'own' || deck.source === 'imported'

function DeckSheet({ slug, onSelect, setNote }) {
  const q = useDeck(slug)
  const [change, setChange] = useState(null)
  const [editing, setEditing] = useState(null)
  const [adding, setAdding] = useState(false)
  const [showVersions, setShowVersions] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  useEffect(() => {
    setChange(null)
    setEditing(null)
    setAdding(false)
  }, [slug])
  if (q.isLoading) return h('div', { className: 'panel', style: { padding: 16 } }, h('p', { className: 'note' }, 'Loading the deck…'))
  if (q.error) return h('div', { className: 'panel', style: { padding: 16 } }, h('p', { className: 'note' }, `The deck did not load: ${q.error.message}`))
  const deck = q.data.deck
  const own = isOwn(deck) && deck.editable !== false
  // GET /decks/{slug} says whether a PUT without a preview saves (your own deck);
  // an imported deck and a backend without the field go through the preview.
  const atOnce = deck.saves_at_once !== undefined ? !!deck.saves_at_once : deck.source === 'own'
  const versionsSlug = deck.edits_save_as || deck.deck
  const saved = out => {
    setChange(null)
    setEditing(null)
    setAdding(false)
    if (out.deck && out.deck !== slug) onSelect(out.deck)
    setNote(savedNote(out, setNote))
  }
  // Your own deck: save at once; anything else (a shipped deck's copy) goes through the preview.
  const apply = async next => {
    if (!atOnce) return setChange(next)
    const { out, error } = await saveAtOnce(deck.deck, next)
    if (out) return saved(out)
    setChange({ ...next, why: error })
    return null
  }
  return h('div', { className: 'panel', style: { minWidth: 0 }, 'data-ubk': 'sheet' },
    h('div', { className: 'sheethead' },
      h('h2', null, h(Mark, { deck }), h('span', { dir: 'auto' }, deck.name)),
      h('span', { className: `badge${own ? ' own' : ''}` }, SOURCE_LABEL[deck.source] || deck.source),
      deck.license && deck.license !== 'own' ? h('span', { className: 'badge' }, deck.license) : null,
      h('span', { className: 'note' }, `by ${deck.by}`),
      h('span', { className: 'grow' }),
      own ? h(Btn, { sm: true, onClick: () => { setAdding(true); setEditing(null) } }, 'New card')
        : h(Btn, { sm: true, onClick: () => setChange({ label: 'your own copy', body: { changes: { meta: { name: deck.name } } } }) }, 'Make my own copy'),
      h(Btn, { text: true, onClick: () => setShowVersions(!showVersions), 'aria-expanded': showVersions }, 'Versions'),
      h(Btn, { text: true, onClick: () => exportDeck(deck.deck) }, 'Export'),
      own ? h(Btn, { text: true, danger: true, onClick: () => setConfirmDelete(true) }, 'Delete deck') : null),
    h('div', { className: 'col', style: { padding: '10px 14px', gap: 10 } },
      deck.description ? h('p', { className: 'muted' }, deck.description) : null,
      !own && deck.edits_save_as ? h('p', { className: 'note' }, 'This deck comes with the plugin. Make your own copy to change it; your copy then takes its place.') : null,
      deck.copy_of ? h('p', { className: 'note' }, `Your copy of ${deck.copy_of}.`) : null,
      showVersions ? h('div', { className: 'col' }, h('div', { className: 'label', style: { margin: 0 } }, 'Versions'),
        h(Versions, { slug: versionsSlug, onRestored: out => setNote({ text: n => `Restored version ${out.restored} of ${n(out.deck)}: ${out.summary}.`, undo: undoFor(out.deck, out.undo, text => setNote({ text })) }) })) : null,
      adding ? h('div', { className: 'panel', style: { padding: 12 } }, h('h3', null, 'New card'),
        h(CardEditor, { initial: { tags: [] }, onCancel: () => setAdding(false), onPreview: v => apply({ label: 'add a card', body: { changes: { add: [v] } } }) })) : null,
      change ? h(PreviewPanel, { slug: deck.deck, change, onCancel: () => setChange(null), onSaved: saved }) : null),
    h(CardsTable, { deck, onChange: apply, editing, setEditing, editable: own }),
    jsx(ConfirmDialog, { open: confirmDelete, onClose: () => setConfirmDelete(false), destructive: true, title: `Delete ${deck.name}?`,
      description: 'The deck leaves the table and the palette. Its versions stay, so Undo or Versions can bring it back.', confirmLabel: 'Delete deck',
      onConfirm: async () => {
        const out = await api.remove(deck.deck)
        afterWrite()
        if (storedPressed() === deck.deck) setPressed('')
        onSelect('')
        setNote({ text: `Deleted ${deck.name || deck.deck}.`, undo: undoFor(deck.deck, out.undo, text => setNote({ text })) })
      } }))
}

export function DecksView({ decksData }) {
  const all = visibleDecks(decksData.decks)
  const [sel, setSel] = useState('')
  const [note, setNote] = useState(null)
  // Deck names by file name, kept after a deck leaves the list (a note after a delete still names it).
  const names = useRef(new Map())
  for (const d of decksData.decks || []) if (d.name) names.current.set(d.deck, d.name)
  const nameOf = slug => names.current.get(slug) || slug
  const [newDeck, setNewDeck] = useState(null) // null | {} (form) | {slug, change} (the preview, when a save at once was refused)
  const current = all.find(d => d.deck === sel) || all[0]
  const toggle = async (d, value) => {
    try {
      await api.setSwitch(d.deck, { draw: value })
      afterWrite()
    } catch (error) {
      toast(`Could not switch ${d.name}: ${error.message}`, 'warning')
    }
  }
  const saveNew = async (slug, change) => {
    const { out, error } = await saveAtOnce(slug, change)
    if (!out) return setNewDeck({ slug, change: { ...change, why: error } })
    setNewDeck(null)
    setSel(out.deck)
    setNote(savedNote(out, setNote))
    return null
  }
  const broken = Object.entries(decksData.broken || {})
  const warned = (decksData.decks || []).filter(d => d.warning)
  return h('div', { className: 'col', style: { gap: 18 } },
    h('div', { className: 'decksheet' },
      h('div', { className: 'col' },
        h('div', { className: 'panel decklist', 'data-ubk': 'decklist' },
          all.map(d => hk(d.deck, 'div', { className: `dl-row${current && current.deck === d.deck ? ' on' : ''}`, 'data-deck': d.deck },
            h('button', { type: 'button', className: 'nm', onClick: () => { setSel(d.deck); setNewDeck(null) } }, h(Mark, { deck: d }), h('span', { dir: 'auto' }, d.name)),
            h('label', { className: 'sw', title: 'Draw from this deck on the Draw tab, the chip and the palette' }, 'Draw',
              jsx(Switch, { size: 'xs', checked: !!(d.switch && d.switch.draw), onCheckedChange: v => toggle(d, v), 'aria-label': `Draw from ${d.name}` })),
            h('span', { className: 'meta' },
              h('span', { className: `badge${isOwn(d) ? ' own' : ''}` }, SOURCE_LABEL[d.source] || d.source),
              h('span', null, `${d.cards} cards`)))),
          h('div', { className: 'row', style: { padding: '8px 9px' } }, h(Btn, { sm: true, onClick: () => setNewDeck({}) }, 'New deck'), h(ImportBox, { decks: decksData.decks, onImported: out => {
            setSel(out.deck)
            // `replaced` is true only when a deck of that file name was there before; an older backend
            // without it answers a replace with undo {restore} and a fresh import with undo {delete}.
            const replaced = out.replaced !== undefined ? !!out.replaced : !!(out.undo && out.undo.restore !== undefined)
            setNote({ text: n => `${replaced ? 'Replaced' : 'Imported'} ${n(out.deck)} (${out.cards} cards). ${out.note || ''}`.trim(), undo: undoFor(out.deck, out.undo, text => setNote({ text })) })
          } }))),
        broken.length ? h('div', { className: 'banner err' }, h('strong', null, 'Not loaded'), broken.map(([s, r]) => hk(s, 'p', { className: 'note' }, `${s}: ${r}`))) : null,
        warned.length ? h('div', { className: 'banner' }, h('strong', null, 'Loaded with a note'), warned.map(d => hk(d.deck, 'p', { className: 'note' }, `${d.deck}: ${d.warning}`))) : null),
      newDeck ? (newDeck.change
        ? h(PreviewPanel, { slug: newDeck.slug, change: newDeck.change, onCancel: () => setNewDeck(null), onSaved: out => {
          setNewDeck(null)
          setSel(out.deck)
          setNote(savedNote(out, setNote))
        } })
        : h(NewDeck, { decks: decksData.decks, onCancel: () => setNewDeck(null), onSave: saveNew }))
        : current ? h(DeckSheet, { slug: current.deck, onSelect: setSel, setNote }) : h('div', { className: 'panel', style: { padding: 16 } }, h('p', { className: 'note' }, 'No decks loaded.'))),
    h(UndoBar, { note, nameOf, onClose: () => setNote(null) }))
}
