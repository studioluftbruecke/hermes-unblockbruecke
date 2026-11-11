// The status-bar chip (F8, Q3): the card of the day (GET /today; hidden when the setting is off);
// "Hermes drew <id>" for 30 s after a new auto-draw in the open chat. The popover shows the card
// (flip), Another (POST /draw context human), Use in chat and Open decks. Palette and shortcut draws
// made away from the UnblockCards page land here too.
import { atom, host, Popover, PopoverContent, PopoverTrigger, useValue } from '@hermes/plugin-sdk'
import { useEffect, useRef, useState } from 'react'
import { jsx } from 'react/jsx-runtime'

import { $connection, dayLocal, whenLocal } from './core.js'
import { useAutoDraw, useToday } from './queries.js'
import { $drawing, $popCard, $popOpen, askHermes, drawCard, openPage, useInChat } from './state.js'
import { Btn, Card, h, Mark } from './ui.js'

const ANNOUNCE_MS = 30000

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

function useAnnouncement() {
  const [stored, runtime] = useFocusedIds()
  const a = useAutoDraw(stored)
  const b = useAutoDraw(runtime)
  const [shown, setShown] = useState(null) // {session, draw}: the chat it happened in, and the draw
  const timer = useRef(null)
  const here = shown && (shown.session === stored || shown.session === runtime)
  const pick = [[stored, a.data], [runtime, b.data]].filter(([id, d]) => id && d && d.draws && d.draws.length)
  const newest = pick.map(([id, d]) => ({ session: id, draw: d.draws[0] })).sort((x, y) => String(y.draw.at).localeCompare(String(x.draw.at)))[0]
  useEffect(() => {
    for (const [id, d] of [[stored, a.data], [runtime, b.data]]) {
      if (id && d && !seen.has(id)) seen.set(id, d.draws && d.draws[0] ? d.draws[0].draw_id : '')
    }
    if (!newest) return
    const base = seen.get(newest.session)
    if (newest.draw.draw_id === base) return
    seen.set(newest.session, newest.draw.draw_id)
    setShown({ session: newest.session, draw: newest.draw })
    clearTimeout(timer.current)
    timer.current = setTimeout(() => setShown(null), ANNOUNCE_MS)
  }, [newest && newest.draw.draw_id, stored, runtime, a.data, b.data])
  // Another chat in focus (or none): the announcement was about the chat the user just left.
  useEffect(() => {
    if (shown && !here) {
      clearTimeout(timer.current)
      setShown(null)
    }
  }, [stored, runtime])
  useEffect(() => () => clearTimeout(timer.current), [])
  return here ? shown.draw : null
}

export function Chip() {
  const conn = useValue($connection)
  const open = useValue($popOpen)
  const pop = useValue($popCard)
  const drawing = useValue($drawing)
  const today = useToday()
  const announce = useAnnouncement()
  const [flipped, setFlipped] = useState(false)
  useEffect(() => setFlipped(false), [pop && pop.draw_id])
  if (conn === 'off' || conn === 'schema') return null
  const day = today.data && today.data.enabled ? today.data.card : null
  const card = pop ? pop.card : announce && announce.view ? announce.view : day
  if (!card && !announce) return null
  const label = announce ? `Hermes drew ${announce.card}` : card.human
  const setOpen = v => {
    $popOpen.set(v)
    if (!v) {
      setFlipped(false)
      $popCard.set(null)
    }
  }
  const act = fn => async () => {
    await fn()
  }
  return jsx(Popover, { open, onOpenChange: setOpen, children: [
    jsx(PopoverTrigger, { asChild: true, children: h('button', { type: 'button', className: `ubkchip${announce ? ' live' : ''}`, 'data-ubk': 'chip',
      title: announce ? `Hermes drew ${announce.card} from ${(announce.view && announce.view.deck_name) || announce.deck} at ${whenLocal(announce.at)}` : pop ? 'The card you drew' : 'Card of the day', 'aria-label': `UnblockBrücke: ${label}` },
      h(Mark, { mark: announce && announce.view ? announce.view.mark : card ? card.mark : 'square' }), h('span', { className: 'tx' }, label)) }, 't'),
    jsx(PopoverContent, { align: 'end', side: 'top', className: 'w-auto', children: card ? h('div', { className: 'ubk pop', 'data-ubk': 'popover' },
      h(Card, { card, flipped, onFlip: () => setFlipped(!flipped), width: 200, size: 'sm' }),
      h('div', { className: 'side' },
        h('p', { className: 'note' }, pop ? `Drawn ${whenLocal(pop.at)}` : `Card of the day${today.data && today.data.date ? `: ${dayLocal(today.data.date)}` : ''}`),
        announce ? h('p', { className: 'note' }, `Hermes drew ${announce.card} in this chat ${whenLocal(announce.at)}.`) : null,
        h(Btn, { sm: true, onClick: () => setFlipped(!flipped) }, flipped ? 'Show human face' : 'Show agent face'),
        h(Btn, { sm: true, onClick: act(() => useInChat(card)) }, 'Use in chat'),
        h(Btn, { sm: true, onClick: act(() => askHermes(card)) }, 'Ask Hermes'),
        h(Btn, { sm: true, disabled: drawing, onClick: act(() => drawCard({ context: 'human', where: 'chip' })) }, 'Another'),
        h(Btn, { sm: true, onClick: () => { setOpen(false); openPage('decks') } }, 'Open decks'))) : h('div', { className: 'ubk' }, h('p', { className: 'note' }, label)) }, 'c'),
  ] })
}
