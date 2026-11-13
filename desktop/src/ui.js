// Small UI helpers, the deck marks and the physical card (0.2 sketch A: card stock, the corner with
// the deck mark and the card number, the front with the line and the deck, the back headed "For
// Hermes", the 3D turn on a click; the card back with the dotted pattern and the deck mark).
import * as SDK from '@hermes/plugin-sdk'
import { jsx, jsxs } from 'react/jsx-runtime'

/** h(tag, props, ...children): jsx without JSX syntax (the bundle is plain ESM). */
export const h = (tag, props, ...children) => {
  const kids = children.flat().filter(c => c !== null && c !== undefined && c !== false)
  return kids.length > 1 ? jsxs(tag, { ...(props || {}), children: kids }) : jsx(tag, { ...(props || {}), children: kids[0] })
}
/** h() with a React key, for elements in a list. */
export const hk = (key, tag, props, ...children) => {
  const kids = children.flat().filter(c => c !== null && c !== undefined && c !== false)
  return kids.length > 1 ? jsxs(tag, { ...(props || {}), children: kids }, key) : jsx(tag, { ...(props || {}), children: kids[0] }, key)
}

/** A button: Desktop's own Button (variants default, secondary, text; sizes sm, default, lg) when the
 *  SDK has it (HX-14), else a plain button in the same look. */
export const Btn = ({ pri, sm, lg, danger, text, strong, children, className, ...rest }) => {
  const Button = SDK.Button
  if (Button) {
    const variant = text ? (strong ? 'textStrong' : 'text') : pri ? 'default' : danger ? 'outline' : 'secondary'
    return jsx(Button, { type: 'button', variant, size: text ? 'inline' : sm ? 'sm' : lg ? 'lg' : 'default', className: ['ubk-btn', danger && 'danger', className].filter(Boolean).join(' '), ...rest, children })
  }
  return h('button', { type: 'button', className: ['btn', pri && 'pri', sm && 'sm', lg && 'lg', danger && 'danger', text && 'text', strong && 'strong', className].filter(Boolean).join(' '), ...rest }, children)
}

// ---- deck marks ----------------------------------------------------------------------------------
// One flat glyph per deck that names its subject (his pick at the sketch, 2026-11-12): a person
// (Human), two chevrons (Coding), a pencil (Writing), a triangle, a square and a circle (Design), a
// shaded sphere (Shaders), a robot head (Agent). Paths from v0.2/sketches/index.html GLYPH, 16 x 16,
// drawn in currentColor. A deck without a subject glyph (own, imported, community) keeps the pip its
// deck file names in `mark` (square, circle, triangle, diamond, half, ring), drawn the same flat way.
let shadeId = 0
const GLYPHS = {
  person: () => [hk('h', 'circle', { cx: 8, cy: 4.3, r: 3.3 }), hk('b', 'path', { d: 'M1.6 15.4a6.4 6.4 0 0 1 12.8 0z' })],
  code: () => h('path', { d: 'M5.4 3 1.4 8l4 5M10.6 3l4 5-4 5', fill: 'none', stroke: 'currentColor', strokeWidth: 2.2, strokeLinecap: 'round', strokeLinejoin: 'round' }),
  pencil: () => h('path', { d: 'M1.2 14.8 5.12 13.92 2.08 10.88zM5.62 13.42 11.35 7.69 8.31 4.65 2.58 10.38zM11.84 7.2 13.47 5.57 10.43 2.53 8.8 4.16z' }),
  shapes: () => [hk('t', 'path', { d: 'M8 .2 12.4 7.6H3.6z' }), hk('s', 'rect', { x: 0.4, y: 9, width: 6.6, height: 6.6, rx: 0.5 }), hk('c', 'circle', { cx: 12.1, cy: 12.3, r: 3.5 })],
  sphere: () => {
    shadeId += 1
    const id = `ubk-shade-${shadeId}`
    return [
      hk('d', 'defs', null, h('radialGradient', { id, cx: 0.3, cy: 0.27, r: 0.85 },
        hk(0, 'stop', { offset: 0, stopColor: 'currentColor', stopOpacity: 0 }),
        hk(1, 'stop', { offset: 0.3, stopColor: 'currentColor', stopOpacity: 0.18 }),
        hk(2, 'stop', { offset: 0.75, stopColor: 'currentColor', stopOpacity: 0.85 }),
        hk(3, 'stop', { offset: 1, stopColor: 'currentColor' }))),
      hk('c', 'circle', { cx: 8, cy: 8, r: 7, fill: `url(#${id})`, stroke: 'currentColor', strokeWidth: 0.9 }),
    ]
  },
  robot: () => [hk('a', 'circle', { cx: 8, cy: 1.5, r: 1.4 }), hk('n', 'rect', { x: 7.3, y: 2.4, width: 1.4, height: 2 }),
    hk('h', 'path', { fillRule: 'evenodd', d: 'M3.4 4.2h9.2a2.6 2.6 0 0 1 2.6 2.6v5.8a2.6 2.6 0 0 1-2.6 2.6H3.4A2.6 2.6 0 0 1 .8 12.6V6.8a2.6 2.6 0 0 1 2.6-2.6zm1.3 3.6v3.6h2.6V7.8zm4 0v3.6h2.6V7.8z' })],
  // The deck file's pips, for decks without a subject glyph.
  square: () => h('rect', { x: 2, y: 2, width: 12, height: 12, rx: 1 }),
  circle: () => h('circle', { cx: 8, cy: 8, r: 6.4 }),
  triangle: () => h('path', { d: 'M8 1.6 14.6 14H1.4z' }),
  diamond: () => h('path', { d: 'M8 1 15 8 8 15 1 8z' }),
  half: () => h('path', { d: 'M1.4 12a6.6 6.6 0 0 1 13.2 0z' }),
  ring: () => h('circle', { cx: 8, cy: 8, r: 5.8, fill: 'none', stroke: 'currentColor', strokeWidth: 2 }),
}

// The six shipped decks by file name, in the chip order he fixed; an own copy (`coding-own`,
// `copy_of: coding`) takes its deck's glyph and place.
export const SUBJECT = { 'human-unblock': 'person', coding: 'code', writing: 'pencil', design: 'shapes', shaders: 'sphere', 'agent-unblock': 'robot' }
const SUBJECT_NAMES = new Set(Object.values(SUBJECT))

/** The shipped deck a summary or card view stands for: its own slug, or the deck it copies. */
export function baseSlug(d) {
  if (!d) return ''
  if (d.copy_of) return String(d.copy_of)
  const slug = String(d.deck || '')
  return /-own$/.test(slug) && SUBJECT[slug.slice(0, -4)] ? slug.slice(0, -4) : slug
}

/** The glyph for a deck summary or a card view: the subject glyph of one of the six decks (or a
 *  deck file that already names one as its mark), else the deck's own pip. */
export function glyphOf(d) {
  if (!d) return 'ring'
  if (d.mark && SUBJECT_NAMES.has(d.mark)) return d.mark
  return SUBJECT[baseSlug(d)] || (GLYPHS[d.mark] ? d.mark : 'square')
}

/** A deck mark: `deck` is a deck summary or a card view ({deck, mark, copy_of?}), or `glyph` names one. */
export const Mark = ({ deck, glyph, className, title }) => {
  const g = glyph || glyphOf(deck)
  const draw = GLYPHS[g] || GLYPHS.square
  return h('span', { className: `ubk-mark mk-${g}${className ? ` ${className}` : ''}`, 'aria-hidden': title ? undefined : 'true', title },
    h('svg', { viewBox: '0 0 16 16', fill: 'currentColor', focusable: 'false' }, draw()))
}

/** Two overlapping cards, 12 px, drawn in currentColor so it follows the theme like Desktop's own
 *  status-bar icons. */
export const CardIcon = ({ size = 12 }) =>
  h('svg', { width: size, height: size, viewBox: '0 0 12 12', fill: 'none', stroke: 'currentColor', strokeWidth: 1.1, 'aria-hidden': 'true', focusable: 'false', className: 'ubk-icon' },
    hk('a', 'rect', { x: 1, y: 2.6, width: 6, height: 8.4, rx: 1, transform: 'rotate(-10 4 6.8)' }),
    hk('b', 'rect', { x: 4.6, y: 1, width: 6, height: 8.4, rx: 1 }))

/** The card number without the deck's short code: 05 for co-05 (his words: the icon and the number
 *  are enough to identify the card). */
export const cardNumber = id => String(id || '').split('-').pop()

const Corner = ({ card, flip }) => flip
  ? h('span', { className: 'idx r180' }, h(Mark, { deck: card }))
  : h('span', { className: 'idx' }, h(Mark, { deck: card }), h('span', null, cardNumber(card.id)))

const deckLabel = card => card.deck_name || card.deck

function FrontFace({ card }) {
  return h('div', { className: 'face front' },
    h('div', { className: 'f-top' }, h(Corner, { card })),
    h('p', { className: 'f-line', dir: 'auto' }, card.human),
    h('div', { className: 'f-bot' }, h('span', { className: 'f-deck', dir: 'auto' }, deckLabel(card)), h(Corner, { card, flip: true })))
}

function RearFace({ card }) {
  return h('div', { className: 'face rear' },
    h('div', { className: 'f-top' }, h(Corner, { card })),
    h('p', { className: 'f-for' }, 'For Hermes'),
    h('p', { className: 'f-instr', dir: 'auto' }, card.agent),
    h('div', { className: 'f-bot' }, h('span', { className: 'f-deck', dir: 'auto' }, deckLabel(card)), h(Corner, { card, flip: true })))
}

export function BackFace({ deck }) {
  return h('div', { className: 'face back' },
    deck ? h(Mark, { deck, className: 'big' }) : null,
    h('span', { className: 'bw' }, 'Unblockbrücke'))
}

/** The card. `flipped` shows the back (For Hermes); a click (or Enter / Space) turns it. With `face`
 *  ('front' or 'rear') it is one still face and no control (the popover, the Hermes tab's example). */
export function Card({ card, flipped, onFlip, width = 300, size, deal, dealKey, face }) {
  const style = { '--w': `${width}px` }
  if (face) {
    return jsx('div', { className: `ubk-card still${face === 'rear' ? ' flipped' : ''}${size ? ` ${size}` : ''}`, style, 'data-card': `${card.deck}/${card.id}`, 'data-face': face,
      children: h('span', { className: 'inner' }, face === 'rear' ? h(RearFace, { card }) : h(FrontFace, { card })) }, dealKey)
  }
  const label = `Card ${cardNumber(card.id)} from ${deckLabel(card)}. ${flipped ? 'Showing what it says for Hermes.' : 'Showing its line.'} Turn it over.`
  return jsx('div', {
    role: 'button',
    tabIndex: 0,
    className: `ubk-card${flipped ? ' flipped' : ''}${size ? ` ${size}` : ''}${deal ? ' deal' : ''}`,
    style,
    'aria-label': label,
    'aria-pressed': !!flipped,
    'data-card': `${card.deck}/${card.id}`,
    'data-face': flipped ? 'rear' : 'front',
    onClick: onFlip,
    onKeyDown: e => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault()
        e.stopPropagation()
        if (onFlip) onFlip()
      }
    },
    children: h('span', { className: 'inner' }, h(FrontFace, { card }), h(RearFace, { card })),
  }, dealKey)
}

/** The card back alone, on a small stack: the table before the first draw, and the loading state. */
export function CardBack({ deck, width = 300, stack = true }) {
  const card = h('div', { className: 'ubk-card still', style: { '--w': `${width}px` }, role: 'img', 'aria-label': 'Card back' },
    h('span', { className: 'inner' }, h(BackFace, { deck })))
  return stack ? h('div', { className: 'ubk-stack', style: { '--w': `${width}px` } }, card) : card
}

export const SOURCE_LABEL = { shipped: 'shipped', community: 'community', own: 'yours', imported: 'imported' }
