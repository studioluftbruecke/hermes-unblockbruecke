// The `card` transcript directive: `::card{deck="coding" id="co-03"}` (optional face="agent")
// renders the card itself inline in an assistant message. Attributes are untrusted model output: a
// deck or id that does not match the contract's patterns, an unknown deck or an unknown card renders
// the directive's source text unchanged. The deck comes from GET /decks/{deck} through React Query, so
// many directives for one deck cost one request. While the message streams, the card back stands in.
import { useState } from 'react'

import { BUILTIN_TAGS, CARD_ID_RE, SLUG_RE } from './core.js'
import { useDeck } from './queries.js'
import { Card, CardBack, h } from './ui.js'

export function validAttrs(attrs) {
  const a = attrs || {}
  const deck = typeof a.deck === 'string' ? a.deck.trim() : ''
  const id = typeof a.id === 'string' ? a.id.trim() : ''
  const face = a.face === undefined || a.face === '' ? 'human' : a.face
  if (!SLUG_RE.test(deck) || !CARD_ID_RE.test(id) || (face !== 'human' && face !== 'agent')) return null
  return { deck, id, face }
}

/** A card view built from a GET /decks/{slug} answer. */
export function viewFromDeck(deck, id, face) {
  const card = (deck.cards || []).find(c => c.id === id)
  if (!card) return null
  const glossary = deck.glossary || {}
  return { deck: deck.deck, deck_name: deck.name, mark: deck.mark, id: card.id, human: card.human, agent: card.agent, tags: card.tags || [], face,
    why: (card.tags || []).map(tag => ({ tag, means: BUILTIN_TAGS[tag] || glossary[tag] || '' })), directive: `::card{deck="${deck.deck}" id="${card.id}"}` }
}

const Source = ({ source }) => h('span', { className: 'ubk-directive-source' }, source)

function Resolved({ attrs, source, streaming }) {
  const q = useDeck(attrs.deck, { staleTime: 300000 })
  const [flipped, setFlipped] = useState(attrs.face === 'agent')
  if (q.isLoading) return h('div', { className: 'ubk inline', 'data-ubk': 'directive' }, h(CardBack, { width: 200, stack: false }))
  const view = q.data && q.data.deck ? viewFromDeck(q.data.deck, attrs.id, attrs.face) : null
  if (!view) return h(Source, { source })
  return h('div', { className: 'ubk inline', 'data-ubk': 'directive' },
    h(Card, { card: view, flipped, onFlip: () => setFlipped(!flipped), width: 200, size: 'sm' }),
    h('span', { className: 'note' }, streaming ? view.deck_name : `${view.deck_name}. Click the card to turn it.`))
}

export function CardDirective({ attrs, source, streaming }) {
  const ok = validAttrs(attrs)
  if (!ok) return h(Source, { source: source || '' })
  return h(Resolved, { attrs: ok, source, streaming })
}
