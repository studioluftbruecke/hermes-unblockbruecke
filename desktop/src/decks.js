// The decks sheet and editor (F12, F13): every deck with its two switches, the selected deck's cards
// with what the journal says about them, and edits that always go preview -> diff -> Save (PUT with the
// preview's confirm value). Versions restore in one click; every save, restore and delete shows Undo.
import { ConfirmDialog, Switch, writeClipboardText } from '@hermes/plugin-sdk'
import { useEffect, useRef, useState } from 'react'
import { jsx } from 'react/jsx-runtime'

import { api } from './api.js'
import { charCount, deckNames, SETTINGS_PATH, SLUG_RE, TAG_RE, toast, whenLocal } from './core.js'
import { refreshPalette } from './palette.js'
import { invalidateDecks, useDeck, useVersions, visibleDecks } from './queries.js'
import { lastDeck, setLastDeck } from './state.js'
import { Btn, h, Mark, SOURCE_LABEL } from './ui.js'

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

function CardEditor({ initial, onPreview, onCancel, submitLabel = 'Preview', blocked = false }) {
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
    h('label', { className: 'col', style: { gap: 3 } }, h('span', { className: 'note' }, 'Tags (1 to 4, comma separated; a new tag gets a plain line in the deck glossary)'),
      h('input', { className: 'inp', value: tags, onChange: e => setTags(e.target.value), 'aria-label': 'Tags', placeholder: 'own' })),
    badTag ? h('p', { className: 'note' }, `"${badTag}" is not a tag: lowercase letters, digits and "-", 2 to 21 characters.`) : null,
    h('div', { className: 'row' },
      h(Btn, { pri: true, disabled: !ok, onClick: () => onPreview({ human: human.trim(), agent: agent.trim(), tags: tagList.length ? tagList : undefined }) }, submitLabel),
      h(Btn, { onClick: onCancel }, 'Cancel')))
}

function CardsTable({ deck, onChange, editing, setEditing }) {
  const cards = deck.cards || []
  return h('div', { className: 'scroll' }, h('table', { className: 'tbl', 'data-ubk': 'cards' },
    h('thead', null, h('tr', null, h('th', null, 'Card'), h('th', null, 'Human face'), h('th', null, 'Agent face'), h('th', null, 'Tags'),
      h('th', { className: 'num' }, 'Drawn'), h('th', { className: 'num' }, 'Helped'), h('th', null, ''))),
    h('tbody', null, cards.map(c => {
      const stats = c.stats || {}
      if (editing === c.id) {
        return jsx('tr', { className: 'editing', children: [jsx('td', { className: 'id', children: c.id }, 'i'),
          jsx('td', { colSpan: 6, children: h(CardEditor, { initial: c, onCancel: () => setEditing(null),
            onPreview: v => onChange({ label: `edit ${c.id}`, body: { changes: { edit: [{ id: c.id, ...v, tags: v.tags || c.tags }] } } }) }) }, 'e')] }, c.id)
      }
      return jsx('tr', { children: [
        jsx('td', { className: 'id', children: c.id }, 'i'),
        jsx('td', { className: 'hf', dir: 'auto', children: c.human }, 'h'),
        jsx('td', { className: 'af', dir: 'auto', children: c.agent }, 'a'),
        jsx('td', { children: h('span', { className: 'tags' }, (c.tags || []).map(t => jsx('span', { children: t }, t))) }, 't'),
        jsx('td', { className: 'num', children: String(stats.drawn ?? 0) }, 'd'),
        jsx('td', { className: 'num', children: String(stats.helped ?? 0) }, 'p'),
        jsx('td', { children: h('span', { className: 'row', style: { flexWrap: 'nowrap', gap: 4 } },
          h(Btn, { sm: true, onClick: () => setEditing(c.id), 'aria-label': `Edit ${c.id}` }, 'Edit'),
          h(Btn, { sm: true, onClick: () => onChange({ label: `remove ${c.id}`, body: { changes: { remove: [c.id] } } }), 'aria-label': `Remove ${c.id}` }, 'Remove')) }, 'x'),
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

async function exportDeck(slug, mode) {
  try {
    const out = await api.exportDeck(slug)
    if (mode === 'copy') {
      await writeClipboardText(out.yaml)
      toast(`Copied ${out.file_name} to the clipboard.`)
      return
    }
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

function ImportBox({ onImported }) {
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
      setState({ ...state, ...extra, error: refusalText(error), exists: error.code === 'exists' || (!!extra.replace && !!state.exists), problems: problemsOf(error.body) })
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
      setState({ ...next, error: refusalText(error), exists: error.code === 'exists', problems: problemsOf(error.body) })
    }
  }
  return h('div', { className: 'panel col', style: { padding: 14 }, 'data-ubk': 'import' },
    h('div', { className: 'label', style: { margin: 0 } }, 'Bring your own'),
    h('div', { className: 'row' },
      h(Btn, { onClick: () => input.current && input.current.click() }, 'Import a deck file'),
      h('input', { ref: input, type: 'file', accept: '.yaml,.yml,text/yaml,application/yaml', style: { display: 'none' }, onChange: pick, 'aria-label': 'Deck file' })),
    h('p', { className: 'note' }, 'Import a deck you own (YAML, the shape of the shipped decks). Imported decks stay on this machine and start switched off for auto-draw.'),
    state && state.error ? h('p', { className: 'note', role: 'alert' }, state.error) : null,
    state && state.problems ? h(ProblemList, { problems: state.problems }) : null,
    state && state.exists ? h('div', { className: 'row' },
      h('input', { className: 'inp', style: { width: 200 }, value: state.slug || '', onChange: e => setState({ ...state, slug: e.target.value }), 'aria-label': 'File name' }),
      h(Btn, { disabled: !SLUG_RE.test(state.slug || ''), onClick: () => send({ slug: state.slug }) }, 'Import under this file name'),
      h(Btn, { danger: true, onClick: () => setConfirmReplace(true) }, 'Replace mine')) : null,
    jsx(ConfirmDialog, { open: confirmReplace, onClose: () => setConfirmReplace(false), destructive: true, title: 'Replace your deck with this file?',
      description: 'The file takes the place of your deck with the same file name. Your version stays under Versions, and Undo brings it back.',
      confirmLabel: 'Replace mine', onConfirm: () => send({ replace: true }, { rethrow: true }) }))
}

/** Why a new deck cannot take this name, or '' when it can. A name or file name already in use would
 *  edit (or copy) that deck instead of making a new one, so it is refused here. */
export function newDeckProblem(name, slug, decks) {
  const n = name.trim()
  if (!n) return 'Give the deck a name.'
  if (charCount(n) > 40) return 'The name can have at most 40 characters.'
  if (!SLUG_RE.test(slug)) return 'The file name needs 2 to 40 lowercase letters, digits or "-".'
  const list = decks || []
  // A deck that comes with the plugin (shipped or community, also while your copy shadows it): its file
  // name and its "-own" file name (where edits of it are saved) belong to it.
  const bundled = s => {
    const d = list.find(x => x.deck === s && (x.source === 'shipped' || x.source === 'community'))
    return d ? d.name || d.deck : ''
  }
  const base = /-own$/.test(slug) ? bundled(slug.slice(0, -4)) : ''
  if (base) return `The file name ${slug} holds your edits of ${base}. Open ${base} and edit it instead.`
  const kept = bundled(slug)
  if (kept) return `The file name ${slug} is taken by ${kept}, which comes with the plugin. Open it and edit it instead.`
  const same = list.find(d => d.deck === slug)
  if (same) return `The file name ${slug} is taken by ${same.name || same.deck}. Pick another name.`
  const named = list.find(d => String(d.name || '').trim().toLowerCase() === n.toLowerCase())
  if (named) return `A deck named ${named.name} is already there. Pick another name.`
  return ''
}

function NewDeck({ decks, onCancel, onPreview }) {
  const [name, setName] = useState('')
  const [slug, setSlug] = useState('')
  const s = slug || slugOf(name)
  const problem = newDeckProblem(name, s, decks)
  return h('div', { className: 'panel col', style: { padding: 14 }, 'data-ubk': 'new-deck', onKeyDown: escapeCancels(onCancel) },
    h('h2', null, 'New deck'),
    h('div', { className: 'row' },
      h('label', { className: 'col grow', style: { gap: 3 } }, h('span', { className: 'note' }, 'Name'), h('input', { className: 'inp', value: name, dir: 'auto', onChange: e => setName(e.target.value), 'aria-label': 'Deck name' })),
      h('label', { className: 'col', style: { gap: 3, width: 200 } }, h('span', { className: 'note' }, 'File name'), h('input', { className: 'inp mono', value: s, onChange: e => setSlug(e.target.value), 'aria-label': 'File name' }))),
    // Always in the tree, empty when the name is fine: a line that came and went would shift the card
    // editor below it to another child position, and React would remount it with an empty draft.
    h('p', { className: 'note', role: 'alert', 'data-ubk': 'new-deck-problem', style: { color: 'var(--ubk-red)', minHeight: '1.4em' } }, name.trim() ? problem : ''),
    h('p', { className: 'note' }, 'Write its first card; you can add more after saving.'),
    h(CardEditor, { initial: { tags: ['own'] }, onCancel, submitLabel: 'Preview the new deck', blocked: !!problem,
      onPreview: v => !problem && onPreview(s, { label: `new deck ${s}`, body: { changes: { meta: { name: name.trim() }, add: [v] } } }) }))
}

// ---- the sheet -----------------------------------------------------------------------------------

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
  const versionsSlug = deck.edits_save_as || deck.deck
  const saved = out => {
    setChange(null)
    setEditing(null)
    setAdding(false)
    if (out.deck && out.deck !== slug) onSelect(out.deck)
    setNote({ text: n => `Saved ${n(out.deck)}: ${out.summary} (version ${out.version}).`, undo: undoFor(out.deck, out.undo, text => setNote({ text })) })
  }
  return h('div', { className: 'panel', style: { minWidth: 0 } },
    h('div', { className: 'sheethead' },
      h('h2', null, h(Mark, { mark: deck.mark }), h('span', { dir: 'auto' }, deck.name)),
      h('span', { className: `badge${deck.source === 'own' || deck.source === 'imported' ? ' own' : ''}` }, SOURCE_LABEL[deck.source] || deck.source),
      h('span', { className: 'badge' }, `v${deck.version}`), deck.license && deck.license !== 'own' ? h('span', { className: 'badge' }, deck.license) : null,
      h('span', { className: 'note' }, `by ${deck.by}`),
      h('span', { className: 'grow' }),
      h(Btn, { sm: true, onClick: () => { setAdding(true); setEditing(null) } }, 'New card'),
      h(Btn, { sm: true, onClick: () => setShowVersions(!showVersions), 'aria-expanded': showVersions }, 'Versions'),
      h(Btn, { sm: true, onClick: () => exportDeck(deck.deck) }, 'Export'),
      h(Btn, { sm: true, onClick: () => exportDeck(deck.deck, 'copy') }, 'Copy YAML'),
      deck.source === 'own' || deck.source === 'imported' ? h(Btn, { sm: true, danger: true, onClick: () => setConfirmDelete(true) }, 'Delete deck') : null),
    h('div', { className: 'col', style: { padding: '10px 14px', gap: 10 } },
      deck.description ? h('p', { className: 'muted' }, deck.description) : null,
      !deck.editable && deck.edits_save_as ? h('p', { className: 'note' }, `This deck ships with the plugin. Edits save as your own copy, ${deck.edits_save_as}, which then replaces it at the table.`) : null,
      deck.copy_of ? h('p', { className: 'note' }, `Your copy of ${deck.copy_of}.`) : null,
      showVersions ? h('div', { className: 'col' }, h('div', { className: 'label', style: { margin: 0 } }, `Versions of ${versionsSlug}`),
        h(Versions, { slug: versionsSlug, onRestored: out => setNote({ text: n => `Restored version ${out.restored} of ${n(out.deck)}: ${out.summary}.`, undo: undoFor(out.deck, out.undo, text => setNote({ text })) }) })) : null,
      adding ? h('div', { className: 'panel', style: { padding: 12 } }, h('h3', null, 'New card'),
        h(CardEditor, { initial: { tags: [] }, onCancel: () => setAdding(false), onPreview: v => setChange({ label: 'add a card', body: { changes: { add: [v] } } }) })) : null,
      change ? h(PreviewPanel, { slug: deck.deck, change, onCancel: () => setChange(null), onSaved: saved }) : null),
    h(CardsTable, { deck, onChange: setChange, editing, setEditing }),
    jsx(ConfirmDialog, { open: confirmDelete, onClose: () => setConfirmDelete(false), destructive: true, title: `Delete ${deck.name}?`,
      description: 'The deck leaves the table and the palette. Its versions stay, so Undo or Versions can bring it back.', confirmLabel: 'Delete deck',
      onConfirm: async () => {
        const out = await api.remove(deck.deck)
        afterWrite()
        if (lastDeck() === deck.deck) setLastDeck('')
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
  const [newDeck, setNewDeck] = useState(null) // null | {} (form) | {slug, change}
  const current = all.find(d => d.deck === sel) || all[0]
  const toggle = async (d, key, value) => {
    try {
      await api.setSwitch(d.deck, { [key]: value })
      afterWrite()
    } catch (error) {
      toast(`Could not switch ${d.name}: ${error.message}`, 'warning')
    }
  }
  const broken = Object.entries(decksData.broken || {})
  const auto = decksData.autodraw || {}
  return h('div', { className: 'col', style: { gap: 18 } },
    h('div', { className: 'decksheet' },
      h('div', { className: 'col' },
        h('div', { className: 'panel decklist', 'data-ubk': 'decklist' },
          all.map(d => jsx('div', { className: `dl-row${current && current.deck === d.deck ? ' on' : ''}`, 'data-deck': d.deck, children: [
            jsx('button', { type: 'button', className: 'nm', onClick: () => { setSel(d.deck); setNewDeck(null) }, children: [jsx(Mark, { mark: d.mark }, 'm'), jsx('span', { dir: 'auto', children: d.name }, 'n')] }, 'b'),
            jsx('span', { className: 'sw', children: [
              jsx('label', { title: 'Draw from this deck at the table, the chip and the palette', children: ['Draw', jsx(Switch, { size: 'xs', checked: !!(d.switch && d.switch.draw), onCheckedChange: v => toggle(d, 'draw', v), 'aria-label': `Draw from ${d.name}` }, 's')] }, 'd'),
              jsx('label', { title: 'Hermes may auto-draw from this deck when it is stuck', children: ['Auto-draw', jsx(Switch, { size: 'xs', checked: !!(d.switch && d.switch.auto), onCheckedChange: v => toggle(d, 'auto', v), 'aria-label': `Auto-draw from ${d.name}` }, 's')] }, 'a'),
            ] }, 's'),
            jsx('span', { className: 'meta', children: [
              jsx('span', { className: `badge${d.source === 'own' || d.source === 'imported' ? ' own' : ''}`, children: SOURCE_LABEL[d.source] || d.source }, 'src'),
              jsx('span', { children: `${d.cards} cards` }, 'c'),
              d.auto_cards ? jsx('span', { children: `${d.auto_cards} for auto-draw` }, 'a') : null,
              d.copy_of ? jsx('span', { children: `copy of ${d.copy_of}` }, 'o') : null,
            ] }, 'm'),
          ] }, d.deck)),
          h('div', { className: 'row', style: { padding: '8px 9px' } }, h(Btn, { sm: true, onClick: () => setNewDeck({}) }, 'New deck'))),
        h('div', { className: 'col', style: { gap: 4 }, 'data-ubk': 'autodraw-note' },
          h('p', { className: 'note' }, auto.on ? `Auto-draw is on: after ${auto.threshold} failed tool calls in a row, Hermes may draw a card.` : 'Auto-draw is off, so the Auto-draw switches do nothing yet.'),
          h('p', { className: 'note' }, `Auto-draw decks: ${deckNames(auto.decks, decksData.decks).join(', ') || 'none'}. A deck with its Auto-draw switch off is left out.`),
          auto.on ? null : h('p', { className: 'note' }, `Turn it on in plugin settings: ${SETTINGS_PATH}.`)),
        broken.length ? h('div', { className: 'banner err' }, h('strong', null, 'Not loaded'), broken.map(([s, r]) => jsx('p', { className: 'note', children: `${s}: ${r}` }, s))) : null),
      newDeck ? (newDeck.change
        ? h(PreviewPanel, { slug: newDeck.slug, change: newDeck.change, onCancel: () => setNewDeck(null), onSaved: out => {
          setNewDeck(null)
          setSel(out.deck)
          setNote({ text: n => `Saved ${n(out.deck)}: ${out.summary} (version ${out.version}).`, undo: undoFor(out.deck, out.undo, text => setNote({ text })) })
        } })
        : h(NewDeck, { decks: decksData.decks, onCancel: () => setNewDeck(null), onPreview: (slug, change) => setNewDeck({ slug, change }) }))
        : current ? h(DeckSheet, { slug: current.deck, onSelect: setSel, setNote }) : h('div', { className: 'panel', style: { padding: 16 } }, h('p', { className: 'note' }, 'No decks loaded.'))),
    h(ImportBox, { onImported: out => {
      setSel(out.deck)
      // `replaced` is true only when a deck of that file name was there before; an older backend
      // without it answers a replace with undo {restore} and a fresh import with undo {delete}.
      const replaced = out.replaced !== undefined ? !!out.replaced : !!(out.undo && out.undo.restore !== undefined)
      setNote({ text: n => `${replaced ? 'Replaced' : 'Imported'} ${n(out.deck)} (${out.cards} cards). ${out.note || ''}`.trim(), undo: undoFor(out.deck, out.undo, text => setNote({ text })) })
    } }),
    h(UndoBar, { note, nameOf, onClose: () => setNote(null) }))
}

