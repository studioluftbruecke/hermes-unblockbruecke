// The Draw button in the status bar and its popover (PLAN-v0.1.3 A17 to A19, P1 to P3). The button is
// the icon and "Draw", nothing else. The popover has three states: before a draw (deck chips, the
// card of the day as one line, Draw), after a draw (the card, Use in chat, Draw another, the page
// link), and Hermes drew in this chat (that card, Use in chat, Draw). A new auto-draw in the focused
// chat puts a dot on the icon until the popover opens or another chat gets focus.
import { atom, host, Popover, PopoverContent, PopoverTrigger, useValue } from '@hermes/plugin-sdk'
import { Component, useEffect, useState } from 'react'
import { jsx } from 'react/jsx-runtime'

import { $connection, log, NAME, whenLocal } from './core.js'
import { drawableDecks, useAutoDraw, useDecks, useToday } from './queries.js'
import { $drawing, $popCard, $popDeck, $popOpen, currentProfile, defaultDeck, drawCard, lastDeck, openPage, setChipMounted, setLastDeck, useInChat } from './state.js'
import { Btn, Card, CardIcon, h, Mark } from './ui.js'

/** Q3: the focused chat's ids. The SDK has both atoms (sdk/index.ts host.state.focusedStoredSessionId,
 *  the durable id the journal's session_id carries, and focusedSessionId, the runtime id); the chip
 *  asks the journal with each distinct one and takes the newest auto-draw. */
function useFocusedIds() {
  const st = host.state || {}
  const stored = useValue(st.focusedStoredSessionId || NULL_ATOM)
  const runtime = useValue(st.focusedSessionId || NULL_ATOM)
  return [stored, runtime !== stored ? runtime : null]
}
const NULL_ATOM = atom(null)

const seen = new Map() // session id -> the draw_id that was newest when the chip first looked

/** P3: the newest auto-draw in the focused chat that arrived while the button was on screen, until
 *  `clear()` (the popover opened) or another chat gets focus. */
function useHermesDrew() {
  const [stored, runtime] = useFocusedIds()
  const a = useAutoDraw(stored)
  const b = useAutoDraw(runtime)
  const [shown, setShown] = useState(null) // {session, draw}: the chat it happened in, and the draw
  const here = shown && (shown.session === stored || shown.session === runtime)
  const pick = [[stored, a.data], [runtime, b.data]].filter(([id, d]) => id && d && d.draws && d.draws.length)
  const newest = pick.map(([id, d]) => ({ session: id, draw: d.draws[0] })).sort((x, y) => String(y.draw.at).localeCompare(String(x.draw.at)))[0]
  useEffect(() => {
    for (const [id, d] of [[stored, a.data], [runtime, b.data]]) {
      if (id && d && !seen.has(id)) seen.set(id, d.draws && d.draws[0] ? d.draws[0].draw_id : '')
    }
    if (!newest) return
    if (newest.draw.draw_id === seen.get(newest.session)) return
    seen.set(newest.session, newest.draw.draw_id)
    setShown({ session: newest.session, draw: newest.draw })
  }, [newest && newest.draw.draw_id, stored, runtime, a.data, b.data])
  // Another chat in focus (or none): the dot was about the chat the user just left.
  useEffect(() => {
    if (shown && !here) setShown(null)
  }, [stored, runtime])
  return [here ? shown.draw : null, () => setShown(null)]
}

/** The chip's own error boundary: the status-bar data item has no Desktop ContribBoundary around it,
 *  and a chip that throws must not take the status bar down. */
export class Boundary extends Component {
  constructor(props) {
    super(props)
    this.state = { failed: false }
  }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  componentDidCatch(error) {
    log('Draw button failed and is hidden until the plugin reloads', String(error))
  }

  render() {
    return this.state.failed ? null : this.props.children
  }
}

export function Chip() {
  const conn = useValue($connection)
  const open = useValue($popOpen)
  const [drew, clearDrew] = useHermesDrew()
  // The card Hermes drew, kept for the popover that opened on the dot.
  const [hermes, setHermes] = useState(null)
  useEffect(() => {
    setChipMounted(true)
    return () => setChipMounted(false)
  }, [])
  if (conn === 'off' || conn === 'schema') return null
  const setOpen = v => {
    if (v && drew) {
      setHermes(drew)
      clearDrew()
    }
    $popOpen.set(v)
    if (!v) {
      setHermes(null)
      $popCard.set(null)
      $popDeck.set(null)
    }
  }
  const tip = drew ? 'Hermes drew a card in this chat' : 'Draw a card'
  return jsx(Popover, { open, onOpenChange: setOpen, children: [
    jsx(PopoverTrigger, { asChild: true, children: h('button', { type: 'button', className: 'ubkchip', 'data-ubk': 'chip', title: tip, 'aria-label': `${NAME}: ${tip.charAt(0).toLowerCase()}${tip.slice(1)}` },
      h('span', { className: 'ic' }, h(CardIcon, null), drew ? h('span', { className: 'dot', 'data-ubk': 'dot', 'aria-hidden': 'true' }) : null),
      h('span', { className: 'tx' }, 'Draw')) }, 't'),
    jsx(PopoverContent, { align: 'end', side: 'top', className: 'w-auto', children: open ? jsx(DrawPopover, { hermes, close: () => setOpen(false) }) : null }, 'c'),
  ] })
}

const isButton = el => !!(el && el.closest && el.closest('button'))

/** The popover body. The deck chips start on defaultDeck() (P1), and every draw from here saves its
 *  deck as this profile's last deck. */
export function DrawPopover({ hermes, close }) {
  const pop = useValue($popCard)
  const picked = useValue($popDeck)
  const drawing = useValue($drawing)
  const decks = useDecks()
  const today = useToday()
  const [flipped, setFlipped] = useState(false)
  useEffect(() => setFlipped(false), [pop && pop.draw_id])
  const all = decks.data && decks.data.decks
  const list = drawableDecks(all)
  const profile = currentProfile()
  const deck = picked && list.some(d => d.deck === picked) ? picked : defaultDeck({ decks: all, profile, last: lastDeck(profile) })
  const draw = async slug => {
    const from = slug === undefined ? deck : slug
    $popDeck.set(from || null)
    if (from) setLastDeck(from, profile)
    await drawCard({ deck: from || '', where: 'chip' })
  }
  const card = pop ? pop.card : hermes && hermes.view ? hermes.view : null
  const state = pop ? 'after' : card ? 'hermes' : 'before'
  const day = today.data && today.data.enabled ? today.data.card : null
  const chips = h('div', { className: 'chips', role: 'group', 'aria-label': 'Deck to draw from' },
    list.map(d => jsx('button', { type: 'button', className: 'deckchip', 'data-deck': d.deck, 'aria-pressed': d.deck === deck, title: d.description || d.name,
      onClick: () => (state === 'after' ? draw(d.deck) : $popDeck.set(d.deck)),
      children: [jsx(Mark, { mark: d.mark }, 'm'), jsx('span', { dir: 'auto', children: d.name }, 'n')] }, d.deck)),
    list.length ? null : h('p', { className: 'note' }, decks.isLoading ? 'Loading the decks…' : 'No deck is switched on for drawing. Switch one on under Decks.'))
  // Enter draws (on a deck chip: from that deck); other buttons keep their own Enter.
  const onKeyDown = e => {
    if (e.key !== 'Enter' || e.defaultPrevented || state === 'after') return
    const chip = e.target && e.target.closest ? e.target.closest('[data-deck]') : null
    if (isButton(e.target) && !chip) return
    e.preventDefault()
    draw(chip ? chip.getAttribute('data-deck') : undefined)
  }
  const link = h('button', { type: 'button', className: 'link', onClick: () => { close(); openPage() } }, `Open ${NAME}`)
  if (state === 'before') {
    return h('div', { className: 'ubk pop before', 'data-ubk': 'popover', 'data-state': state, onKeyDown },
      chips,
      day ? h('button', { type: 'button', className: 'today', 'data-ubk': 'today', title: 'Show the card of the day',
        onClick: () => $popCard.set({ card: day, draw_id: `today-${today.data.date || ''}`, at: new Date().toISOString(), today: true }) },
        h('span', { className: 'k' }, 'Today:'), ' ', h('span', { className: 'tx', dir: 'auto' }, day.human)) : null,
      h('div', { className: 'row' }, h(Btn, { pri: true, sm: true, disabled: drawing || !list.length, onClick: () => draw() }, drawing ? 'Drawing…' : 'Draw'), h('span', { className: 'grow' }), link))
  }
  return h('div', { className: 'ubk pop', 'data-ubk': 'popover', 'data-state': state, onKeyDown },
    chips,
    h('div', { className: 'deal' },
      h('div', { className: 'turnable' },
        h(Card, { card, flipped, onFlip: () => setFlipped(!flipped), width: 200, size: 'sm' }),
        h('span', { className: 'hint', 'aria-hidden': 'true' }, flipped ? 'Click to turn back' : 'Click to turn')),
      h('div', { className: 'side' },
        state === 'hermes' ? h('p', { className: 'note' }, `Hermes drew this in this chat, ${whenLocal(hermes.at)}.`) : null,
        h(Btn, { pri: true, sm: true, onClick: () => useInChat(card) }, 'Use in chat'),
        state === 'hermes'
          ? h(Btn, { sm: true, disabled: drawing || !list.length, onClick: () => draw() }, 'Draw')
          : h(Btn, { sm: true, disabled: drawing, onClick: () => draw(pop.today ? deck : card.deck) }, 'Draw another'),
        link)))
}
