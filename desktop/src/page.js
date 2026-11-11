// The Unblockbrücke page (/unblockbruecke): three views chosen by the query string (?view=table|decks|journal),
// and the one-sentence states for a backend that is not on, not reachable, or does not match.
import { useValue } from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'
import { jsx } from 'react/jsx-runtime'

import { $connection, NOT_ON_TEXT, OFFLINE_TEXT, PATH, SCHEMA_TEXT } from './core.js'
import { DecksView } from './decks.js'
import { JournalView } from './journal.js'
import { useDecks } from './queries.js'
import { TableView } from './table.js'
import { h } from './ui.js'

const VIEWS = [['table', 'Table'], ['decks', 'Decks'], ['journal', 'Journal']]

export function viewFromHash(hash) {
  const q = String(hash || '').split('?')[1] || ''
  const v = new URLSearchParams(q).get('view')
  return VIEWS.some(([id]) => id === v) ? v : 'table'
}

function useView() {
  const [view, setView] = useState(() => viewFromHash(window.location.hash))
  useEffect(() => {
    const on = () => setView(viewFromHash(window.location.hash))
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])
  const go = v => {
    window.location.hash = `#${PATH}${v === 'table' ? '' : `?view=${v}`}`
    setView(v)
  }
  return [view, go]
}

/** The state line for a backend that cannot answer, or null when it can. */
export function ConnectionNote({ error }) {
  const conn = useValue($connection)
  let text = null
  if (conn === 'off' || (error && error.notOn)) text = NOT_ON_TEXT
  else if (conn === 'schema' || (error && error.schema)) text = SCHEMA_TEXT
  else if (conn === 'offline' || (error && error.network)) text = OFFLINE_TEXT
  if (!text) return null
  return h('div', { className: 'banner err', role: 'status', 'data-ubk': 'connection' }, text)
}

export function CardsPage() {
  const [view, go] = useView()
  const decks = useDecks()
  const conn = useValue($connection)
  const blocked = (decks.error && (decks.error.notOn || decks.error.schema || decks.error.network)) || conn === 'off' || conn === 'schema'
  return h('div', { className: 'ubk page', 'data-view': view },
    h('div', { className: 'head' },
      h('h1', null, 'Unblockbrücke'),
      h('span', { className: 'muted small' }, 'Cards to unblock yourself or your agent.'),
      h('span', { className: 'grow' }),
      h('div', { className: 'seg', role: 'tablist', 'aria-label': 'View' }, VIEWS.map(([id, label]) =>
        jsx('button', { type: 'button', role: 'tab', 'aria-selected': view === id, 'aria-pressed': view === id, onClick: () => go(id), children: label }, id)))),
    h('div', { className: 'body' },
      blocked || (decks.error && !decks.data) ? h('div', { className: 'col', style: { maxWidth: 720 } },
        h(ConnectionNote, { error: decks.error }),
        decks.error && !decks.error.notOn && !decks.error.schema && !decks.error.network ? h('div', { className: 'banner err' }, `The decks did not load: ${decks.error.message}`) : null)
        : !decks.data ? h('p', { className: 'note' }, 'Loading the decks…')
          : view === 'decks' ? h(DecksView, { decksData: decks.data })
            : view === 'journal' ? h(JournalView, null)
              : h(TableView, { decks: decks.data.decks })))
}
