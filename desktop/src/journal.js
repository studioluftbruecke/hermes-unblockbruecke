// The journal (F10, F11): every draw with who drew it, the card, what happened next and the rating;
// totals, a filter by who drew, and the learning reset.
import { ConfirmDialog, queryClient } from '@hermes/plugin-sdk'
import { useState } from 'react'
import { jsx } from 'react/jsx-runtime'

import { api } from './api.js'
import { qk, toast, whenLocal } from './core.js'
import { useJournal } from './queries.js'
import { Btn, BY_LABEL, h, Mark } from './ui.js'

/** "What happened next" in plain words, from the outcome lines (contract §4). */
export function nextText(d) {
  const n = d.next || {}
  const parts = []
  if (n.status === 'ok') parts.push(`The next call${n.tool ? ` (${n.tool})` : ''} worked.`)
  else if (n.status === 'failed') parts.push(`The next call${n.tool ? ` (${n.tool})` : ''} failed too.`)
  if (typeof n.calls_to_recover === 'number') parts.push(`Recovered after ${n.calls_to_recover} call${n.calls_to_recover === 1 ? '' : 's'}.`)
  if (parts.length) return parts.join(' ')
  if (d.by === 'auto') return d.tool ? `Drawn after ${d.streak || 'several'} failed calls (${d.tool}); waiting for the next call.` : 'Waiting for the next call.'
  if (d.by === 'agent') return 'Hermes drew it in chat.'
  return d.context === 'day' ? 'Card of the day.' : 'Drawn by hand.'
}

export async function rateDraw(drawId, rating) {
  try {
    await api.rate(drawId, rating)
    queryClient.invalidateQueries({ queryKey: qk('journal') })
    queryClient.invalidateQueries({ queryKey: qk('deck') })
  } catch (error) {
    toast(`Could not save the rating: ${error.message}`, 'warning')
  }
}

export function ResetLearning({ learning }) {
  const [open, setOpen] = useState(false)
  return h('span', { className: 'row' },
    h(Btn, { sm: true, onClick: () => setOpen(true) }, 'Reset learning'),
    jsx(ConfirmDialog, { open, onClose: () => setOpen(false), title: 'Start learning again?',
      description: `Cards will be drawn with equal weight again, and new ratings count from now on. The journal itself stays.${learning === false ? ' Learning is off right now, so weights are not used until you switch it on.' : ''}`,
      confirmLabel: 'Reset learning',
      onConfirm: async () => {
        const out = await api.reset()
        queryClient.invalidateQueries({ queryKey: qk() })
        toast(`Learning starts again from ${whenLocal(out.reset_at)}. The journal stays.`)
      } }))
}

const FILTERS = [['', 'All'], ['user', 'You'], ['agent', 'Hermes'], ['auto', 'Auto-draw']]

export function JournalView() {
  const [by, setBy] = useState('')
  const q = useJournal({ by })
  const data = q.data
  const draws = (data && data.draws) || []
  const t = (data && data.totals) || {}
  return h('div', { className: 'panel', style: { minWidth: 0 }, 'data-ubk': 'journal' },
    h('div', { className: 'sheethead' }, h('h2', null, 'Journal'), h('span', { className: 'grow' }),
      h('div', { className: 'seg', role: 'group', 'aria-label': 'Drawn by' }, FILTERS.map(([v, label]) => jsx('button', { type: 'button', 'aria-pressed': by === v, onClick: () => setBy(v), children: label }, v || 'all'))),
      h(ResetLearning, { learning: data && data.learning })),
    q.isLoading ? h('p', { className: 'note', style: { padding: 14 } }, 'Loading the journal…') : null,
    q.error ? h('p', { className: 'note', style: { padding: 14 } }, `The journal did not load: ${q.error.message}`) : null,
    data && !draws.length ? h('p', { className: 'note', style: { padding: 14 } }, by ? 'No draws of this kind yet.' : 'No draws yet. Every card you or Hermes draw lands here.') : null,
    draws.length ? h('div', { className: 'scroll' }, h('table', { className: 'tbl' },
      h('thead', null, h('tr', null, h('th', null, 'When'), h('th', null, 'Drawn by'), h('th', null, 'Card'), h('th', null, 'What happened next'), h('th', null, 'Helped'))),
      h('tbody', null, draws.map(d => {
        const v = d.view
        return jsx('tr', { 'data-draw': d.draw_id, children: [
          jsx('td', { className: 'id', title: d.at, children: whenLocal(d.at) }, 'w'),
          jsx('td', { children: h('span', { className: 'who' }, h(Mark, { mark: d.by === 'user' ? 'circle' : 'square' }), BY_LABEL[d.by] || d.by) }, 'b'),
          jsx('td', { className: 'jcard', dir: 'auto', children: [v ? v.human : `${d.card} (no longer in ${d.deck})`,
            jsx('small', { children: `${d.card} · ${v ? v.deck_name : d.deck}` }, 's')] }, 'c'),
          jsx('td', { className: 'muted', children: nextText(d) }, 'n'),
          jsx('td', { children: d.rating ? h('span', { className: `rated ${d.rating === 'helped' ? 'y' : 'n'}` }, d.rating === 'helped' ? 'helped' : 'not now')
            : h('span', { className: 'row', style: { flexWrap: 'nowrap', gap: 4 } },
              h(Btn, { sm: true, onClick: () => rateDraw(d.draw_id, 'helped'), 'aria-label': `Card ${d.card} helped` }, 'Helped'),
              h(Btn, { sm: true, onClick: () => rateDraw(d.draw_id, 'not_now'), 'aria-label': `Card ${d.card}: not now` }, 'Not now')) }, 'r'),
        ] }, d.draw_id)
      })))) : null,
    data ? h('div', { className: 'stats', 'data-ubk': 'totals' },
      `${t.draws ?? 0} draws, ${t.helped ?? 0} helped, ${t.not_now ?? 0} not now, ${t.by_auto ?? 0} by auto-draw. `,
      data.learning ? 'Learning is on: cards that helped come up a little more often.' : 'Learning is off: every card has the same chance.') : null)
}
