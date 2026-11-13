// The Draw tab (0.2 sketch A, "card stage"): the deck chips in his fixed order with exactly one
// pressed, the card in the middle, one action after a draw ("Pass it to Hermes") and "Draw another",
// and under the card a short list: your earlier draws (the one before asks "Helped" or "Not this
// time" once) or the cards that helped. Keys: F turns the card, D draws.
import { useValue } from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'

import { RateButtons, ResetLearning } from './history.js'
import { useJournal } from './queries.js'
import { $asking, $drawing, $pressedRev, $rated, $session, $table, ALL, chipList, drawCard, flipTable, passToHermes, pressedChip, setPressed, storedPressed } from './state.js'
import { Btn, Card, CardBack, h, hk, Mark } from './ui.js'

const isEditable = el => !!el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName))
// Earlier draws shown under the card (sketch A: two lines).
const EARLIER = 2

/** The row of deck chips. `pressed` is the one pressed key; a press changes the choice only. */
export function DeckChips({ decks, pressed, onPress }) {
  return h('div', { className: 'chips', role: 'group', 'aria-label': 'Decks to draw from', 'data-ubk': 'chips' },
    chipList(decks).map(c => hk(c.key, 'button', { type: 'button', className: 'chip', 'data-deck': c.key, 'aria-pressed': c.key === pressed, onClick: () => onPress(c.key), title: c.deck ? c.deck.description || c.name : 'Every deck switched on for drawing' },
      c.deck ? h(Mark, { deck: c.deck }) : null, h('span', { dir: 'auto' }, c.name))))
}

/** One journal row (or a draw of this window) as a line: mark, the card's line, then a rating ask or a badge. */
function Line({ row, ask, rated }) {
  const v = row.view || row.card
  const rating = rated || row.rating
  const tail = ask && !rating ? h(RateButtons, { drawId: row.draw_id, label: v ? v.human : row.card })
    : rating === 'helped' ? h('span', { className: 'badge' }, 'Helped') : null
  return h('li', { 'data-draw': row.draw_id },
    v ? h(Mark, { deck: v, title: v.deck_name || v.deck }) : h('span', null),
    h('span', { className: 'ln', dir: 'auto' }, v ? v.human : row.card),
    tail)
}

/** Your draws for the list under the card: this window's draws first (the journal may not have them
 *  yet), then the journal's, newest first, without the card on the table. */
export function earlierRows(session, journal, tableId) {
  const seen = new Set([tableId])
  const out = []
  for (const r of [...session.map(s => ({ draw_id: s.draw_id, at: s.at, view: s.card })), ...((journal && journal.draws) || [])]) {
    if (!r || seen.has(r.draw_id)) continue
    seen.add(r.draw_id)
    out.push(r)
  }
  return out
}

/** The cards you marked as helped, each card once, newest first. */
export function helpedRows(rows, rated) {
  const seen = new Set()
  return rows.filter(r => {
    const rating = rated[r.draw_id] || r.rating
    const v = r.view || {}
    const k = `${v.deck || r.deck}/${v.id || r.card}`
    if (rating !== 'helped' || seen.has(k)) return false
    seen.add(k)
    return true
  })
}

export function DrawView({ decks }) {
  useValue($pressedRev)
  const table = useValue($table)
  const drawing = useValue($drawing)
  const session = useValue($session)
  const asking = useValue($asking)
  const rated = useValue($rated)
  const journal = useJournal({ by: 'user' })
  const [helpedView, setHelpedView] = useState(false)
  const pressed = pressedChip(decks, storedPressed())
  const chips = chipList(decks)
  const canDraw = chips.length > 1
  const pressedDeck = (chips.find(c => c.key === pressed) || {}).deck || null
  const draw = () => drawCard({ deck: pressed, where: 'table' })

  useEffect(() => {
    const onKey = e => {
      if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.altKey || isEditable(e.target) || isEditable(document.activeElement)) return
      const k = e.key.toLowerCase()
      if (k === 'f') {
        e.preventDefault()
        flipTable()
      } else if (k === 'd') {
        e.preventDefault()
        draw()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  const card = table && table.card
  const rows = earlierRows(session, journal.data, table && table.draw_id)
  const helped = helpedRows(rows, rated)
  const list = helpedView ? helped : rows.slice(0, EARLIER)
  return h('div', { className: 'stage', 'data-ubk': 'draw' },
    h(DeckChips, { decks, pressed, onPress: key => setPressed(key) }),
    canDraw ? null : h('p', { className: 'note' }, 'No deck is switched on for drawing. Switch one on under Decks.'),
    card ? h(Card, { card, flipped: table.flipped, onFlip: flipTable, width: 300, deal: true, dealKey: table.n })
      : h(CardBack, { deck: pressed === ALL ? null : pressedDeck, width: 300 }),
    h('div', { className: 'acts' },
      card ? h(Btn, { pri: true, lg: true, onClick: () => passToHermes(card) }, 'Pass it to Hermes') : null,
      h(Btn, { pri: !card, lg: true, onClick: draw, disabled: drawing || !canDraw }, card ? 'Draw another' : 'Draw')),
    rows.length || helped.length ? h('section', { className: 'hist', 'data-ubk': helpedView ? 'helped' : 'earlier' },
      h('header', null,
        h('h2', null, helpedView ? 'Cards that helped' : 'Earlier'),
        h(Btn, { text: true, 'aria-pressed': helpedView, onClick: () => setHelpedView(!helpedView) }, helpedView ? 'Earlier' : `Cards that helped ${helped.length}`)),
      list.length ? h('ul', { className: 'lines' }, list.map(r => hk(r.draw_id, Line, { row: r, ask: !helpedView && r.draw_id === asking, rated: rated[r.draw_id] })))
        : h('p', { className: 'note' }, 'None yet. Mark a card as helped when it did.'),
      helpedView ? h('div', { className: 'hist-foot' }, h(ResetLearning, { learning: journal.data && journal.data.learning })) : null) : null)
}
