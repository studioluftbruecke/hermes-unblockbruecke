// Every route this Desktop half calls, one function each, exactly as the pinned contract lists them
// (experiments/unblockbruecke/v0.1-contract.md §5). No other file calls rest(); the build test reads
// this file and checks every path against the contract table.
import { opId, rest } from './core.js'

const enc = encodeURIComponent
const post = (path, body) => rest(path, { method: 'POST', body: { op_id: opId(), ...(body || {}) } })
const put = (path, body) => rest(path, { method: 'PUT', body: { op_id: opId(), ...(body || {}) } })

export const api = {
  health: () => rest('/health'),
  decks: () => rest('/decks'),
  deck: slug => rest(`/decks/${enc(slug)}`),
  draw: body => post('/draw', body),
  today: () => rest('/today'),
  journal: ({ limit = 50, by = '', session = '' } = {}) => {
    const q = new URLSearchParams({ limit: String(limit) })
    if (by) q.set('by', by)
    if (session) q.set('session', session)
    return rest(`/journal?${q.toString()}`)
  },
  rate: (drawId, rating) => post('/journal/rate', { draw_id: drawId, rating }),
  reset: () => post('/journal/reset', {}),
  preview: (slug, body) => rest(`/decks/${enc(slug)}/preview`, { method: 'POST', body }),
  save: (slug, body) => put(`/decks/${enc(slug)}`, body),
  versions: slug => rest(`/decks/${enc(slug)}/versions`),
  restore: (slug, version) => post(`/decks/${enc(slug)}/restore`, { version }),
  remove: slug => post(`/decks/${enc(slug)}/delete`, {}),
  importDeck: body => post('/decks/import', body),
  exportDeck: slug => rest(`/decks/${enc(slug)}/export`),
  settings: () => rest('/settings'),
  setSwitch: (deck, sw) => put('/settings/decks', { deck, ...sw }),
}
