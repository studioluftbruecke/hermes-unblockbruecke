// Shared state and actions every surface uses: the card on the table, the draws of this session,
// the Draw popover, the default deck, drawing (page, popover, palette, shortcut), and handing a card
// to chat.
import { atom, host, queryClient } from '@hermes/plugin-sdk'

import { api } from './api.js'
import { getCtx, ID, isPagePath, log, PATH, qk, storage, toast } from './core.js'
import { drawableDecks } from './queries.js'

// The card on the table: {card, draw_id, at, flipped, n}. `n` changes on every draw (the deal motion).
export const $table = atom(null)
// The last six draws of this Desktop session, newest first.
export const $session = atom([])
// The Draw popover: open flag, the card it shows after a draw, and the deck chip picked in it.
export const $popOpen = atom(false)
export const $popCard = atom(null)
export const $popDeck = atom(null)
export const $drawing = atom(false)

// True while the Draw button is on screen (Chip mounted). A hidden button is not rendered at all
// (Desktop's right-click menu, show_in_statusbar, or the whole bar hidden), so a draw meant for the
// popover goes to the page instead of a popover nobody sees.
let chipMounted = false
export const setChipMounted = on => {
  chipMounted = !!on
}

let dealt = 0

/** Draw a card (POST /draw, journal `by: user`) and show it where the user is: the table when the
 *  Unblockbrücke page is open, else the Draw popover, else (button hidden) the page. `deck` undefined
 *  means the default deck (`defaultDeck`); '' or null means any deck. Returns the answer, or null
 *  after a toast. */
export async function drawCard({ deck, context, where } = {}) {
  if ($drawing.get()) return null
  $drawing.set(true)
  try {
    const slug = deck === undefined ? await resolveDefaultDeck() : deck
    const body = {}
    if (slug) body.deck = slug
    if (context) body.context = context
    const out = await api.draw(body)
    if (!out || !out.card) return out
    dealt += 1
    const item = { card: out.card, draw_id: out.draw_id, at: new Date().toISOString(), flipped: false, n: dealt }
    $table.set(item)
    $session.set([item, ...$session.get().filter(x => x.draw_id !== out.draw_id)].slice(0, 6))
    const target = where || (isPagePath() ? 'table' : 'chip')
    if (target === 'chip' && chipMounted) {
      $popCard.set(item)
      $popOpen.set(true)
    } else if (target === 'chip') {
      openPage()
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
  host.navigate(view && view !== 'table' ? `${PATH}?view=${view}` : PATH)
}

/** The text "Use in chat" puts into the composer: the card's directive line (renders the card in
 *  Desktop's transcript; the agent reads it as the card) and the human face as a quote. */
export const chatText = card => `${card.directive || `::card{deck="${card.deck}" id="${card.id}"}`}\n"${card.human}"`
export const askText = card => `I drew Unblockbrücke card ${card.id} (${card.deck_name || card.deck}): "${card.human}". Help me use it on what I am working on.`

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

/** "Use in chat": append the card to the active composer's draft. Never sends. When no composer is
 *  on screen (the Unblockbrücke page fills the main pane), open the focused chat (else a new one) first. */
export async function useInChat(card) {
  const text = chatText(card)
  const c = host.composer
  if (!c || typeof c.setDraft !== 'function') return copyFallback(text, 'This Desktop has no composer door for plugins.')
  try {
    const before = await c.getDraft(null)
    const next = before && before.trim() ? `${before.replace(/\s+$/, '')}\n\n${text}` : text
    if (await c.setDraft(null, next)) {
      toast(`Card ${card.id} is in the chat composer. Press send when you are ready.`)
      return true
    }
    const stored = host.state.focusedStoredSessionId ? host.state.focusedStoredSessionId.get() : null
    if (stored && typeof host.openSession === 'function') await host.openSession(stored)
    else host.newChat()
    const prev = stored ? await c.getDraft(null).catch(() => null) : null
    const ok = await fillUntil(prev && prev.trim() ? `${prev.replace(/\s+$/, '')}\n\n${text}` : text)
    if (ok) toast(`Card ${card.id} is in the chat composer. Press send when you are ready.`)
    else await copyFallback(text, 'No chat composer answered.')
    return ok
  } catch (error) {
    await copyFallback(text, `Could not reach the composer (${error.message}).`)
    return false
  }
}

/** "Ask Hermes" (F16): a new chat with the card drafted; the user presses send. */
export async function askHermes(card) {
  const text = askText(card)
  if (!host.composer || typeof host.newChat !== 'function') return copyFallback(text, 'This Desktop cannot open a chat for plugins.')
  host.newChat()
  const ok = await fillUntil(text)
  if (!ok) await copyFallback(text, 'The new chat did not take the draft.')
  return ok
}

/** The profile a deck choice belongs to: the focused chat's owner profile, else the profile Desktop
 *  is bound to, else 'default'. A Desktop without focusedSessionProfile falls through. */
export function currentProfile() {
  const st = host.state || {}
  const read = a => (a && typeof a.get === 'function' ? a.get() : null)
  return read(st.focusedSessionProfile) || read(st.profile) || 'default'
}

// The last deck per profile (A22): one key the page, the popover and the shortcut all read and write.
// Nothing is copied from the 0.1.2 key `deck`.
const deckKey = profile => `deck:${profile || currentProfile()}`
export const lastDeck = profile => storage.get(deckKey(profile), '')
export const setLastDeck = (slug, profile) => storage.set(deckKey(profile), slug || '')

/** P1: the deck the popover, the shortcut and the palette's "Draw a card" start from. In order: the
 *  last deck drawn in this profile while it is still drawable; a drawable deck named like the profile
 *  (`coding`, `shader` -> `shaders`, `designs` -> `design`); Human unblock; else undefined (any deck). */
export function defaultDeck({ decks, profile, last }) {
  const slugs = new Set(drawableDecks(decks).map(d => d.deck))
  if (last && slugs.has(last)) return last
  const p = String(profile || '').toLowerCase()
  for (const s of p ? [p, `${p}s`, p.endsWith('s') ? p.slice(0, -1) : ''] : []) if (s && slugs.has(s)) return s
  return slugs.has('human-unblock') ? 'human-unblock' : undefined
}

/** defaultDeck() with the live deck list. Uses the list the palette keeps in the query cache while it
 *  is younger than 30 s, and reads it again when it is older: a switch turned off from plugin
 *  settings, a tool or another window must not be drawn from by name. A last deck that is off or gone
 *  is forgotten, so the next press does not try it again. */
export async function resolveDefaultDeck() {
  const profile = currentProfile()
  const last = lastDeck(profile)
  let data
  try {
    data = await queryClient.fetchQuery({ queryKey: qk('decks'), queryFn: api.decks, staleTime: 30000, retry: false })
  } catch (error) {
    log('decks not read, drawing from any deck', error.message)
    return undefined
  }
  const decks = data && data.decks
  if (last && !drawableDecks(decks).some(d => d.deck === last)) setLastDeck('', profile)
  return defaultDeck({ decks, profile, last })
}

export { ID }
