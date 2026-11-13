// Shared state and actions every surface uses: the card on the table, the pressed deck chip, the
// chip's popover, drawing (page, popover, palette, shortcut), and passing a card to Hermes.
import { atom, host, queryClient } from '@hermes/plugin-sdk'

import { api } from './api.js'
import { getCtx, ID, isPagePath, log, PATH, qk, storage, toast } from './core.js'
import { drawableDecks } from './queries.js'
import { baseSlug, SUBJECT } from './ui.js'

// The card on the table: {card, draw_id, at, flipped, n}. `n` changes on every draw (the deal motion).
export const $table = atom(null)
// The draw that asks "Helped" or "Not this time" once: the card that was on the table when the next
// one was drawn, until it is rated or the next draw after it.
export const $asking = atom(null)
// The chip's popover: open flag, and a card drawn from the palette or the shortcut while the page was not open.
export const $popOpen = atom(false)
export const $popCard = atom(null)
export const $drawing = atom(false)
// The draws of this Desktop window, newest first: Earlier shows them before the journal answers again.
export const $session = atom([])
// Ratings given in this window by draw_id, so a rated row changes at once.
export const $rated = atom({})
export const noteRating = (drawId, rating) => $rated.set({ ...$rated.get(), [drawId]: rating })
// Bumped when the pressed chip changes, so every surface that reads it renders again.
export const $pressedRev = atom(0)

// True while the chip is on screen (mounted). A hidden chip is not rendered at all (Desktop's
// right-click menu, or the whole bar hidden), so a draw meant for the popover goes to the page.
let chipMounted = false
export const setChipMounted = on => {
  chipMounted = !!on
}

// ---- the deck chips --------------------------------------------------------------------------------
// His rules at the sketch (2026-11-12): one fixed order that never moves, exactly one chip pressed (a
// deck, or All for every deck), Human on a first run, and pressing a chip draws nothing by itself.
export const ALL = 'all'
export const FIRST_DECK = 'human-unblock'
export const CHIP_ORDER = Object.keys(SUBJECT)

/** The chips for a GET /decks list: every deck with its Draw switch on, the six shipped decks first in
 *  his order (an own copy takes its deck's place), then other decks by name, then All. The order
 *  depends only on the decks, never on which chip is pressed. */
export function chipList(decks) {
  const rank = d => {
    const i = CHIP_ORDER.indexOf(baseSlug(d))
    return i >= 0 ? i : CHIP_ORDER.length
  }
  const list = drawableDecks(decks).slice().sort((a, b) => rank(a) - rank(b) || String(a.name).localeCompare(String(b.name)) || a.deck.localeCompare(b.deck))
  return [...list.map(d => ({ key: d.deck, name: d.name, deck: d })), { key: ALL, name: 'All', deck: null }]
}

/** The profile a deck choice belongs to: the focused chat's owner profile, else the profile Desktop
 *  is bound to, else 'default'. */
export function currentProfile() {
  const st = host.state || {}
  const read = a => (a && typeof a.get === 'function' ? a.get() : null)
  return read(st.focusedSessionProfile) || read(st.profile) || 'default'
}

// One stored choice per profile: a deck's file name or 'all'. Nothing is carried over from 0.1's
// `deck:<profile>` key (there '' meant any deck, a choice the chips no longer offer as such).
const pressedKey = profile => `pressed:${profile || currentProfile()}`
export const storedPressed = profile => storage.get(pressedKey(profile), '') || ''
export function setPressed(key, profile) {
  storage.set(pressedKey(profile), key || '')
  $pressedRev.set($pressedRev.get() + 1)
}

/** The chip that is pressed for a deck list: the stored choice while it is still a chip, else Human
 *  (or the deck that stands in its place), else All. Always exactly one. */
export function pressedChip(decks, stored) {
  const chips = chipList(decks)
  if (stored && chips.some(c => c.key === stored)) return stored
  const human = chips.find(c => c.deck && baseSlug(c.deck) === FIRST_DECK)
  return human ? human.key : ALL
}

let dealt = 0

/** Draw a card (POST /draw, journal `by: user`) from the pressed chip and show it where the user is:
 *  the table when the page is open, else the popover, else (chip hidden) the page. `deck` undefined
 *  means the pressed chip; 'all' means every deck. Returns the answer, or null after a toast. */
export async function drawCard({ deck, context, where } = {}) {
  if ($drawing.get()) return null
  $drawing.set(true)
  try {
    const key = deck === undefined ? await resolvePressed() : deck
    const body = {}
    if (key && key !== ALL) body.deck = key
    if (context) body.context = context
    const out = await api.draw(body)
    if (!out || !out.card) return out
    dealt += 1
    const before = $table.get()
    const item = { card: out.card, draw_id: out.draw_id, at: new Date().toISOString(), flipped: false, n: dealt }
    $session.set([item, ...$session.get().filter(x => x.draw_id !== out.draw_id)].slice(0, 12))
    const target = where || (isPagePath() ? 'table' : 'chip')
    if (target === 'table') {
      // The card that was on the table asks once, now that the next one is drawn.
      $asking.set(before && !$rated.get()[before.draw_id] ? before.draw_id : null)
      $table.set(item)
    } else {
      $table.set(item)
      if (chipMounted) {
        $popCard.set(item)
        $popOpen.set(true)
      } else {
        openPage()
      }
    }
    queryClient.invalidateQueries({ queryKey: qk('journal') })
    return out
  } catch (error) {
    toast(error.code === 'no_card' || /no card/i.test(error.message) ? 'No card to draw: switch a deck on under Decks.' : `Could not draw: ${error.message}`, 'warning')
    return null
  } finally {
    $drawing.set(false)
  }
}

export const flipTable = () => {
  const t = $table.get()
  if (t) $table.set({ ...t, flipped: !t.flipped })
}

export function openPage(view) {
  host.navigate(view && view !== 'draw' ? `${PATH}?view=${view}` : PATH)
}

/** The message "Pass it to Hermes" drafts: the card's directive line, the front and the back, so
 *  Hermes starts the move without a lookup (M0 P4's `both` text). */
export const handoffText = card => [
  card.directive || `::card{deck="${card.deck}" id="${card.id}"}`,
  `I drew "${card.human}" (${card.deck_name || card.deck}).`,
  `For Hermes: ${card.agent}`,
].join('\n')

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms))

async function fillUntil(text, tries = 24) {
  for (let i = 0; i < tries; i++) {
    try {
      await host.composer.setDraft(null, text)
      const now = await host.composer.getDraft(null)
      if (now === text) return true
    } catch (error) {
      log('setDraft retry', String(error))
    }
    await sleep(250)
  }
  return false
}

async function copyFallback(text, why) {
  let ok = false
  try {
    const ctx = getCtx()
    ok = ctx && ctx.os ? await ctx.os.writeClipboard(text) : false
  } catch {
    ok = false
  }
  toast(ok ? `${why} The card is on the clipboard; paste it into a chat.` : `${why} Paste this into a chat: ${text}`, 'warning')
}

const DRAFTED = 'The card is in the chat, front and back. Nothing is sent: press send when you are ready.'

/** "Pass it to Hermes": draft one message with both faces into the chat in focus, or a new chat when
 *  none is on screen. Never sends. */
export async function passToHermes(card) {
  const text = handoffText(card)
  const c = host.composer
  if (!c || typeof c.setDraft !== 'function') return copyFallback(text, 'This Desktop has no composer door for plugins.')
  try {
    const before = await c.getDraft(null)
    const next = before && before.trim() ? `${before.replace(/\s+$/, '')}\n\n${text}` : text
    if (before !== null && await c.setDraft(null, next)) {
      toast(DRAFTED)
      return true
    }
    const stored = host.state.focusedStoredSessionId ? host.state.focusedStoredSessionId.get() : null
    if (stored && typeof host.openSession === 'function') await host.openSession(stored)
    else host.newChat()
    const prev = stored ? await c.getDraft(null).catch(() => null) : null
    const ok = await fillUntil(prev && prev.trim() ? `${prev.replace(/\s+$/, '')}\n\n${text}` : text)
    if (ok) toast(DRAFTED)
    else await copyFallback(text, 'No chat composer answered.')
    return ok
  } catch (error) {
    await copyFallback(text, `Could not reach the composer (${error.message}).`)
    return false
  }
}

/** The pressed chip with the live deck list (the shortcut, the palette's "Draw a card", the popover's
 *  Another). Uses the list in the query cache while it is younger than 30 s and reads it again when
 *  older: a deck switched off elsewhere must not be drawn from by name. */
export async function resolvePressed() {
  const profile = currentProfile()
  let data
  try {
    data = await queryClient.fetchQuery({ queryKey: qk('decks'), queryFn: api.decks, staleTime: 30000, retry: false })
  } catch (error) {
    log('decks not read, drawing from every deck', error.message)
    return ALL
  }
  return pressedChip(data && data.decks, storedPressed(profile))
}

export { ID }
