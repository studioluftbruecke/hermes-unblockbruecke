// The card table (F3, F16): pick a deck, draw, turn the card, put it into chat or ask Hermes about it,
// see why it was drawn and the last six draws of this session. Keys: F turns, D draws.
import { useValue } from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'
import { jsx } from 'react/jsx-runtime'

import { BUILTIN_TAGS, whenLocal } from './core.js'
import { drawableDecks } from './queries.js'
import { $drawing, $session, $table, askHermes, drawCard, flipTable, lastDeck, setLastDeck, useInChat } from './state.js'
import { Btn, Card, CardBack, h, Mark } from './ui.js'

const isEditable = el => !!el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName))

export function TableView({ decks }) {
  const table = useValue($table)
  const session = useValue($session)
  const drawing = useValue($drawing)
  const [deck, setDeck] = useState(lastDeck())
  const [why, setWhy] = useState(false)
  const list = drawableDecks(decks)
  const chosen = list.find(d => d.deck === deck) || null
  const pick = slug => {
    setDeck(slug)
    setLastDeck(slug)
  }
  const draw = () => {
    setWhy(false)
    return drawCard({ deck: chosen ? chosen.deck : '', where: 'table' })
  }

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
  const total = list.reduce((n, d) => n + (d.cards || 0), 0)
  return h('div', { className: 'draw' },
    h('div', null,
      h('div', { className: 'label' }, 'Deck'),
      h('div', { className: 'decks', role: 'group', 'aria-label': 'Deck to draw from' },
        h('button', { type: 'button', className: 'decksel', 'aria-pressed': !chosen, onClick: () => pick('') },
          h(Mark, { mark: 'ring' }), h('span', null, 'Any deck'), h('span', { className: 'c' }, String(total)),
          h('small', null, 'Every deck switched on for drawing')),
        list.map(d => jsx('button', { type: 'button', className: 'decksel', 'aria-pressed': chosen ? chosen.deck === d.deck : false, onClick: () => pick(d.deck), title: d.description || d.name,
          children: [jsx(Mark, { mark: d.mark }, 'm'), jsx('span', { dir: 'auto', children: d.name }, 'n'), jsx('span', { className: 'c', children: String(d.cards) }, 'c'),
            d.description ? jsx('small', { dir: 'auto', children: d.description }, 's') : null] }, d.deck))),
      list.length ? null : h('p', { className: 'note', style: { marginTop: 10 } }, 'No deck is switched on for drawing. Switch one on under Decks.'),
      h('p', { className: 'note', style: { marginTop: 14, paddingTop: 12, borderTop: '1px solid var(--ubk-line)' } }, 'Area decks are small on purpose. Five good cards beat thirty vague ones.')),
    h('div', { className: 'felt' },
      h('div', { className: 'ubk-stack' },
        card ? h(Card, { card, flipped: table.flipped, onFlip: flipTable, width: 300, deal: true, dealKey: table.n })
          : h(CardBack, { mark: chosen ? chosen.mark : 'ring', deckName: chosen ? chosen.name : 'Any deck', width: 300 })),
      h('div', { className: 'actions' },
        h(Btn, { pri: true, onClick: draw, disabled: drawing || !list.length }, drawing ? 'Drawing…' : 'Draw'),
        h(Btn, { onClick: flipTable, disabled: !card }, card && table.flipped ? 'Show human face' : 'Show agent face'),
        h(Btn, { onClick: () => card && useInChat(card), disabled: !card }, 'Use in chat'),
        h(Btn, { onClick: () => card && askHermes(card), disabled: !card }, 'Ask Hermes'),
        h(Btn, { onClick: () => setWhy(!why), disabled: !card, 'aria-expanded': why }, 'Why this card?')),
      why && card ? h('div', { className: 'why', 'data-ubk': 'why' },
        h('span', { className: 'note' }, 'Its tags, in plain words:'),
        whyRows(card).map(w => jsx('div', { children: [jsx('b', { children: w.tag }, 't'), ' ', w.means || 'No explanation in this deck yet.'] }, w.tag))) : null,
      h('p', { className: 'note' }, 'Click the card or press ', h('kbd', null, 'F'), ' to turn it. ', h('kbd', null, 'D'), ' draws. Every draw is in the journal.')),
    h('div', { className: 'aside' },
      h('div', null,
        h('div', { className: 'label' }, 'On the table'),
        card ? h('dl', { className: 'kv' },
          h('dt', null, 'Deck'), h('dd', null, card.deck_name || card.deck),
          h('dt', null, 'Card'), h('dd', { className: 'mono' }, card.id),
          h('dt', null, 'Face'), h('dd', null, table.flipped ? 'Agent' : 'Human'),
          h('dt', null, 'Tags'), h('dd', null, h('span', { className: 'tags' }, (card.tags || []).map(t => jsx('span', { children: t }, t)))),
          h('dt', null, 'Drawn'), h('dd', null, whenLocal(table.at)),
          h('dt', null, 'In chat'), h('dd', { className: 'mono small', style: { overflowWrap: 'anywhere' } }, card.directive || ''))
          : h('p', { className: 'note' }, 'Nothing yet. Draw a card.')),
      h('div', null,
        h('div', { className: 'label' }, 'Drawn this session'),
        session.length ? h('ul', { className: 'recent' }, session.map(s => jsx('li', { children: h('button', { type: 'button', onClick: () => $table.set({ ...s, flipped: false }), title: 'Put it back on the table' },
          h(Mark, { mark: s.card.mark }), h('span', { className: 'tx', dir: 'auto' }, s.card.human), h('span', { className: 't' }, s.card.id)) }, s.draw_id)))
          : h('p', { className: 'note' }, 'Your draws in this window show up here.'))))
}

export function whyRows(card) {
  const rows = Array.isArray(card.why) && card.why.length ? card.why : (card.tags || []).map(tag => ({ tag, means: '' }))
  return rows.map(w => ({ tag: w.tag, means: w.means || BUILTIN_TAGS[w.tag] || '' }))
}
