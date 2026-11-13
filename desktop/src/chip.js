// The chip in the status bar and its popover (0.2 sketch A). The chip carries the card of the day:
// its icon and the card's line. When Hermes drew a card in the chat in focus, the chip shows that
// card's line with a dot until it is clicked, the next turn starts, or another chat gets focus. The
// popover holds the card, "Pass it to Hermes", "Another" and a link to the page; after Hermes drew,
// the card with "Helped" and "Not this time". The chip asks the journal about Hermes' draws only
// while "Hermes draws when stuck" is on (HX-15).
import { atom, host, Popover, PopoverContent, PopoverTrigger, useValue } from '@hermes/plugin-sdk'
import { Component, useEffect, useRef, useState } from 'react'
import { jsx } from 'react/jsx-runtime'

import { $connection, log, NAME } from './core.js'
import { RateButtons } from './history.js'
import { settingsOf, useAutoDraw, useSettings, useToday } from './queries.js'
import { $drawing, $popCard, $popOpen, drawCard, openPage, passToHermes, setChipMounted } from './state.js'
import { Btn, Card, CardBack, CardIcon, h } from './ui.js'

const NULL_ATOM = atom(null)
const FALSE_ATOM = atom(false)

/** Q3: the focused chat's ids. The journal's session_id carries the stored id; the runtime id is asked
 *  too, and the newest draw by Hermes in either wins. */
function useFocusedIds() {
  const st = host.state || {}
  const stored = useValue(st.focusedStoredSessionId || NULL_ATOM)
  const runtime = useValue(st.focusedSessionId || NULL_ATOM)
  return [stored, runtime !== stored ? runtime : null]
}

const seen = new Map() // session id -> the draw_id that was newest when the chip first looked

/** The newest draw by Hermes in the focused chat that arrived while the chip was on screen, until
 *  `clear()` (the chip was clicked), the next turn starts, or another chat gets focus. */
export function useHermesDrew(on) {
  const [stored, runtime] = useFocusedIds()
  const busy = useValue((host.state && host.state.busy) || FALSE_ATOM)
  const a = useAutoDraw(stored, on)
  const b = useAutoDraw(runtime, on)
  const [shown, setShown] = useState(null) // {session, draw, wasBusy}
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
    setShown({ session: newest.session, draw: newest.draw, idle: !busy })
  }, [newest && newest.draw.draw_id, stored, runtime, a.data, b.data])
  // The next turn starts: the focused chat goes busy again after it was idle with the card shown.
  const prevBusy = useRef(busy)
  useEffect(() => {
    if (shown && !busy && !shown.idle) setShown({ ...shown, idle: true })
    else if (shown && busy && !prevBusy.current && shown.idle) setShown(null)
    prevBusy.current = busy
  }, [busy])
  // Another chat in focus (or none): the dot was about the chat the user just left.
  useEffect(() => {
    if (shown && !here) setShown(null)
  }, [stored, runtime])
  // The feature switched off: nothing is shown.
  useEffect(() => {
    if (!on && shown) setShown(null)
  }, [on])
  return [here ? shown.draw : null, () => setShown(null)]
}

/** The chip's own error boundary: the status-bar item has no Desktop ContribBoundary around it, and a
 *  chip that throws must not take the status bar down. */
export class Boundary extends Component {
  constructor(props) {
    super(props)
    this.state = { failed: false }
  }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  componentDidCatch(error) {
    log('The chip failed and is hidden until the plugin reloads', String(error))
  }

  render() {
    return this.state.failed ? null : this.props.children
  }
}

export function Chip() {
  const conn = useValue($connection)
  const open = useValue($popOpen)
  const settings = useSettings()
  const s = settingsOf(settings.data)
  const [drew, clearDrew] = useHermesDrew(!!(s && s.autodraw))
  const today = useToday()
  // The card Hermes drew, kept for the popover that opened on it.
  const [hermes, setHermes] = useState(null)
  useEffect(() => {
    setChipMounted(true)
    return () => setChipMounted(false)
  }, [])
  if (conn === 'off' || conn === 'schema') return null
  const day = today.data && today.data.enabled ? today.data.card : null
  const setOpen = v => {
    if (v && drew) {
      setHermes(drew)
      clearDrew()
    }
    $popOpen.set(v)
    if (!v) {
      setHermes(null)
      $popCard.set(null)
    }
  }
  const line = drew && drew.view ? drew.view.human : day ? day.human : ''
  const kind = drew ? 'Hermes drew a card' : day ? 'Card of the day' : 'Draw a card'
  return jsx(Popover, { open, onOpenChange: setOpen, children: [
    jsx(PopoverTrigger, { asChild: true, children: h('button', { type: 'button', className: 'ubkchip', 'data-ubk': 'chip', title: line ? `${kind}: ${line}` : kind, 'aria-label': `${NAME}, ${kind.toLowerCase()}${line ? `: ${line}` : ''}` },
      h('span', { className: 'ic' }, h(CardIcon, null), drew ? h('span', { className: 'dot', 'data-ubk': 'dot', 'aria-hidden': 'true' }) : null),
      h('span', { className: 'tx', dir: 'auto' }, line || 'Draw')) }, 't'),
    jsx(PopoverContent, { align: 'end', side: 'top', className: 'w-auto', children: open ? jsx(ChipPopover, { hermes, day, close: () => setOpen(false) }) : null }, 'c'),
  ] })
}

/** The popover: the card Hermes drew (rate it), a card drawn from the palette or Another, the card of
 *  the day, or (card of the day off, nothing drawn) the card back and Draw. */
export function ChipPopover({ hermes, day, close }) {
  const pop = useValue($popCard)
  const drawing = useValue($drawing)
  const another = () => drawCard({ where: 'chip' })
  const link = view => h('button', { type: 'button', className: 'lnk', onClick: () => { close(); openPage(view) } }, `Open ${NAME}`)
  if (hermes && !pop) {
    const card = hermes.view
    const n = hermes.streak || ''
    return h('div', { className: 'ubk pop', 'data-ubk': 'popover', 'data-state': 'hermes' },
      card ? h(Card, { card, face: 'front', width: 150, size: 'xs' }) : null,
      h('div', { className: 'col' },
        h('p', { className: 'ph' }, n ? `Hermes drew this after ${n} failed calls.` : 'Hermes drew this card.'),
        h('div', { className: 'btns' }, h(RateButtons, { drawId: hermes.draw_id, label: card ? card.human : hermes.card, onRated: close, boxed: true })),
        link('hermes')))
  }
  const card = pop ? pop.card : day
  if (!card) {
    return h('div', { className: 'ubk pop', 'data-ubk': 'popover', 'data-state': 'empty' },
      h(CardBack, { width: 150, stack: false }),
      h('div', { className: 'col' },
        h('p', { className: 'ph' }, 'Draw a card'),
        h('div', { className: 'btns' }, h(Btn, { pri: true, disabled: drawing, onClick: another }, 'Draw')),
        link()))
  }
  return h('div', { className: 'ubk pop', 'data-ubk': 'popover', 'data-state': pop ? 'drawn' : 'day' },
    jsx(Card, { card, face: 'front', width: 150, size: 'xs' }, `${card.deck}/${card.id}`),
    h('div', { className: 'col' },
      h('p', { className: 'ph' }, pop ? 'Your card' : 'Card of the day'),
      h('div', { className: 'btns' },
        h(Btn, { pri: true, onClick: () => { close(); passToHermes(card) } }, 'Pass it to Hermes'),
        h(Btn, { disabled: drawing, onClick: another }, 'Another')),
      link()))
}
