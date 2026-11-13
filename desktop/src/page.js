// The Unblockbrücke page (/unblockbruecke): three tabs named for who they serve, chosen by the query
// string (?view=draw|hermes|decks; 0.1's table and journal open Draw and Hermes), and the one-sentence
// states for a backend that is not on, not reachable, or does not match.
import * as SDK from '@hermes/plugin-sdk'
import { useValue } from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'
import { jsx } from 'react/jsx-runtime'

import { $connection, NOT_ON_TEXT, OFFLINE_TEXT, SCHEMA_TEXT } from './core.js'
import { DecksView } from './decks.js'
import { DrawView } from './draw.js'
import { HermesView } from './hermes.js'
import { useDecks } from './queries.js'
import { openPage } from './state.js'
import { h, hk } from './ui.js'

export const VIEWS = [['draw', 'Draw'], ['hermes', 'Hermes'], ['decks', 'Decks']]
const OLD = { table: 'draw', journal: 'hermes' }

export function viewFromHash(hash) {
  const q = String(hash || '').split('?')[1] || ''
  const raw = new URLSearchParams(q).get('view')
  const v = OLD[raw] || raw
  return VIEWS.some(([id]) => id === v) ? v : 'draw'
}

function useView() {
  const [view, setView] = useState(() => viewFromHash(window.location.hash))
  useEffect(() => {
    const on = () => setView(viewFromHash(window.location.hash))
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])
  const go = v => {
    openPage(v)
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

/** Desktop's Tabs when the SDK has them, else tab buttons in the same look. */
function TabBar({ view, go }) {
  const { Tabs, TabsList, TabsTrigger } = SDK
  if (Tabs && TabsList && TabsTrigger) {
    return jsx(Tabs, { value: view, onValueChange: go, className: 'tabs', children: jsx(TabsList, { 'aria-label': 'Unblockbrücke', children: VIEWS.map(([id, label]) => jsx(TabsTrigger, { value: id, children: label }, id)) }) })
  }
  return h('div', { className: 'tabs', role: 'tablist', 'aria-label': 'Unblockbrücke' },
    VIEWS.map(([id, label]) => hk(id, 'button', { type: 'button', role: 'tab', 'aria-selected': view === id, onClick: () => go(id) }, label)))
}

export function CardsPage() {
  const [view, go] = useView()
  const decks = useDecks()
  const conn = useValue($connection)
  const blocked = (decks.error && (decks.error.notOn || decks.error.schema || decks.error.network)) || conn === 'off' || conn === 'schema'
  return h('div', { className: 'ubk page', 'data-view': view },
    h('header', { className: 'head' },
      h('div', { className: 'ti' }, h('h1', null, 'Unblockbrücke'), h('span', { className: 'sub' }, 'Cards to unblock yourself or your agent.')),
      h(TabBar, { view, go })),
    h('div', { className: 'body' },
      blocked || (decks.error && !decks.data) ? h('div', { className: 'col', style: { maxWidth: 720 } },
        h(ConnectionNote, { error: decks.error }),
        decks.error && !decks.error.notOn && !decks.error.schema && !decks.error.network ? h('div', { className: 'banner err' }, `The decks did not load: ${decks.error.message}`) : null)
        : !decks.data ? h('p', { className: 'note' }, 'Loading the decks…')
          : view === 'decks' ? h(DecksView, { decksData: decks.data })
            : view === 'hermes' ? h(HermesView, { decksData: decks.data })
              : h(DrawView, { decks: decks.data.decks })))
}
