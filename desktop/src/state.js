// Shared state and actions every surface uses: the card on the table, the draws of this session,
// the chip popover, drawing (page, chip, palette, shortcut), and handing a card to chat.
import { atom, host, queryClient } from '@hermes/plugin-sdk'

import { api } from './api.js'
import { getCtx, ID, isPagePath, log, PATH, qk, storage, toast } from './core.js'
import { drawableDecks } from './queries.js'

// The card on the table: {card, draw_id, at, flipped, n}. `n` changes on every draw (the deal motion).
export const $table = atom(null)
// The last six draws of this Desktop session, newest first.
export const $session = atom([])
// The status-bar popover: open flag and the card it shows instead of the card of the day.
export const $popOpen = atom(false)
export const $popCard = atom(null)
export const $drawing = atom(false)

let dealt = 0

/** Draw a card (POST /draw, journal `by: user`) and show it where the user is: the table when the
 *  Unblockbrücke page is open, else the chip popover. Returns the answer, or null after a toast. */
export async function drawCard({ deck, context, where } = {}) {
  if ($drawing.get()) return null
  $drawing.set(true)
  try {
    const body = {}
    if (deck) body.deck = deck
    if (context) body.context = context
    const out = await api.draw(body)
    if (!out || !out.card) return out
    dealt += 1
    const item = { card: out.card, draw_id: out.draw_id, at: new Date().toISOString(), flipped: false, n: dealt }
    $table.set(item)
    $session.set([item, ...$session.get().filter(x => x.draw_id !== out.draw_id)].slice(0, 6))
    const target = where || (isPagePath() ? 'table' : 'chip')
    if (target === 'chip') {
      $popCard.set(item)
      $popOpen.set(true)
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

export const lastDeck = () => storage.get('deck', '')
export const setLastDeck = slug => storage.set('deck', slug || '')

/** The deck the shortcut draws from: the table's choice while that deck is still switched on for
 *  drawing (same filter as the table), else Any deck; a deck that is off or gone is forgotten, so the
 *  next press does not try it again. Uses the deck list the palette keeps in the query cache while it
 *  is younger than 30 s, and reads it again when it is older: a switch turned off from plugin settings,
 *  a tool or another window must not be drawn from by name. */
export async function shortcutDeck() {
  const slug = lastDeck()
  if (!slug) return undefined
  let data
  try {
    data = await queryClient.fetchQuery({ queryKey: qk('decks'), queryFn: api.decks, staleTime: 30000, retry: false })
  } catch (error) {
    log('shortcut: decks not read, drawing from any deck', error.message)
    return undefined
  }
  if (drawableDecks(data && data.decks).some(d => d.deck === slug)) return slug
  setLastDeck('')
  return undefined
}
export { ID }
