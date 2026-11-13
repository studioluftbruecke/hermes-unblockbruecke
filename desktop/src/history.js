// The journal's pieces both tabs use: a rating, the learning reset, and the facts of one of Hermes'
// draws (where the turn ran, what the next call did), worded as facts.
import { ConfirmDialog, queryClient } from '@hermes/plugin-sdk'
import { useState } from 'react'
import { jsx } from 'react/jsx-runtime'

import { api } from './api.js'
import { qk, toast, whenLocal } from './core.js'
import { $asking, noteRating } from './state.js'
import { Btn, h } from './ui.js'

export async function rateDraw(drawId, rating) {
  try {
    await api.rate(drawId, rating)
    noteRating(drawId, rating)
    if ($asking.get() === drawId) $asking.set(null)
    queryClient.invalidateQueries({ queryKey: qk('journal') })
    queryClient.invalidateQueries({ queryKey: qk('deck') })
    return true
  } catch (error) {
    toast(`Could not save the rating: ${error.message}`, 'warning')
    return false
  }
}

/** "Helped" and "Not this time": two underlined text buttons in a list, two plain buttons with `boxed`
 *  (the popover); `label` names the card for screen readers. */
export function RateButtons({ drawId, label, onRated, boxed }) {
  const rate = async rating => {
    if (await rateDraw(drawId, rating) && onRated) onRated(rating)
  }
  return h('span', { className: 'rate' },
    h(Btn, { text: !boxed, strong: true, onClick: () => rate('helped'), 'aria-label': `${label}: helped` }, 'Helped'),
    h(Btn, { text: !boxed, strong: true, onClick: () => rate('not_now'), 'aria-label': `${label}: not this time` }, 'Not this time'))
}

export function ResetLearning({ learning }) {
  const [open, setOpen] = useState(false)
  return h('span', { className: 'row' },
    h(Btn, { text: true, onClick: () => setOpen(true) }, 'Reset learning'),
    jsx(ConfirmDialog, { open, onClose: () => setOpen(false), title: 'Start learning again?',
      description: `Cards will be drawn with equal weight again, and new ratings count from now on. The journal itself stays.${learning === false ? ' Learning is off right now, so weights are not used until you switch it on.' : ''}`,
      confirmLabel: 'Reset learning',
      onConfirm: async () => {
        const out = await api.reset()
        queryClient.invalidateQueries({ queryKey: qk() })
        toast(`Learning starts again from ${whenLocal(out.reset_at)}. The journal stays.`)
      } }))
}

// Where the turn of one of Hermes' draws ran (v0.2-contract.md §4): the row's `where_label`, else its
// `where` in the same words; a row written by 0.1 says nothing.
const WHERE = {
  desktop: 'Desktop chat', kanban: 'Kanban task', cron: 'Cron job', cli: 'CLI', subagent: 'Delegated task', api: 'API',
  editor: 'Editor', messaging: 'Chat', unknown: 'Unknown',
}
export function whereText(d) {
  if (d && typeof d.where_label === 'string' && d.where_label) return d.where_label
  const raw = String((d && d.where) || '').toLowerCase()
  return raw ? WHERE[raw] || raw : ''
}

/** What the next call did, as a fact (AX-4): "Next call ok", "Next call failed", or nothing yet. The
 *  0.2 row's `next_call`, else 0.1's `next.status`. */
export function nextFact(d) {
  const s = d && (d.next_call || (d.next && d.next.status))
  if (s === 'ok') return { tone: 'ok', text: 'Next call ok' }
  if (s === 'failed') return { tone: 'bad', text: 'Next call failed' }
  return { tone: 'none', text: 'No next call yet' }
}
