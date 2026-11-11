// Small UI helpers, the deck mark and the physical card (mockups/concept.html: card stock, index
// corners, the 3D flip from the human face to the agent face "Do this", the card back with the dotted
// pattern and the deck mark).
import { jsx, jsxs } from 'react/jsx-runtime'

/** h(tag, props, ...children): jsx without JSX syntax (the bundle is plain ESM). */
export const h = (tag, props, ...children) => {
  const kids = children.flat().filter(c => c !== null && c !== undefined && c !== false)
  return kids.length > 1 ? jsxs(tag, { ...(props || {}), children: kids }) : jsx(tag, { ...(props || {}), children: kids[0] })
}

export const Btn = ({ pri, sm, danger, children, className, ...rest }) =>
  h('button', { type: 'button', className: ['btn', pri && 'pri', sm && 'sm', danger && 'danger', className].filter(Boolean).join(' '), ...rest }, children)

const MARKS = new Set(['square', 'circle', 'triangle', 'diamond', 'half', 'ring'])
export const markClass = mark => `ubk-mark mk-${MARKS.has(mark) ? mark : 'square'}`
export const Mark = ({ mark, className, style }) => h('span', { className: `${markClass(mark)}${className ? ` ${className}` : ''}`, style, 'aria-hidden': 'true' })

const Index = ({ card, flip }) => h('span', { className: `idx${flip ? ' flip180' : ''}` }, h(Mark, { mark: card.mark }), h('span', null, card.id))

function HumanFace({ card, side }) {
  return h('div', { className: `face human ${side}` },
    h('div', { className: 'f-top' }, h(Index, { card }), h('span', { className: 'f-kind' }, 'Human')),
    h('p', { className: 'f-line', dir: 'auto' }, card.human),
    h('div', { className: 'f-bot' }, h('span', { className: 'f-deck', dir: 'auto' }, card.deck_name || card.deck), h(Index, { card, flip: true })))
}

// The 200 px card shows two tags and a count; the rest are in the popover's and the table's lists.
const SM_TAGS = 2

function AgentFace({ card, side, size }) {
  const tags = card.tags || []
  const shown = size === 'sm' && tags.length > SM_TAGS ? tags.slice(0, SM_TAGS) : tags
  return h('div', { className: `face agent ${side}` },
    h('div', { className: 'f-top' }, h(Index, { card }), h('span', { className: 'f-kind' }, 'Agent')),
    h('p', { className: 'f-instr', dir: 'auto' }, card.agent),
    h('div', { className: 'f-tags' }, shown.map(t => jsx('span', { children: t }, t)),
      shown.length < tags.length ? jsx('span', { className: 'more', title: tags.slice(shown.length).join(', '), children: `+${tags.length - shown.length}` }, '+') : null),
    h('div', { className: 'f-bot' }, h('span', { className: 'f-deck', dir: 'auto' }, card.deck_name || card.deck), h(Index, { card, flip: true })))
}

export function BackFace({ mark, deckName, side = 'front' }) {
  return h('div', { className: `face back ${side}` },
    h('span', { className: `${markClass(mark)} big`, 'aria-hidden': 'true' }),
    h('span', { className: 'bw' }, 'Unblockbrücke'),
    deckName ? h('span', { className: 'bd' }, deckName) : null)
}

/** The card itself. `flipped` shows the agent face; a click (or Enter / Space) turns it. */
export function Card({ card, flipped, onFlip, width = 300, size, deal, dealKey }) {
  const label = `Card ${card.id} from ${card.deck_name || card.deck}, ${flipped ? 'agent' : 'human'} face. Click to turn.`
  return jsx('div', {
    role: 'button',
    tabIndex: 0,
    className: `ubk-card${flipped ? ' flipped' : ''}${size ? ` ${size}` : ''}${deal ? ' deal' : ''}`,
    style: { '--w': `${width}px` },
    'aria-label': label,
    'aria-pressed': !!flipped,
    'data-card': `${card.deck}/${card.id}`,
    'data-face': flipped ? 'agent' : 'human',
    onClick: onFlip,
    onKeyDown: e => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault()
        e.stopPropagation()
        if (onFlip) onFlip()
      }
    },
    children: h('span', { className: 'inner' }, h(HumanFace, { card, side: 'front' }), h(AgentFace, { card, side: 'rear', size })),
  }, dealKey)
}

/** The card back alone: the stack before the first draw, and the loading state. */
export function CardBack({ mark, deckName, width = 300 }) {
  return h('div', { className: 'ubk-card', style: { '--w': `${width}px`, cursor: 'default' }, 'aria-label': 'Card back' },
    h('span', { className: 'inner' }, h(BackFace, { mark, deckName })))
}

export const SOURCE_LABEL = { shipped: 'shipped', community: 'community', own: 'yours', imported: 'imported' }
export const BY_LABEL = { user: 'You', agent: 'Hermes, asked', auto: 'Auto-draw' }
