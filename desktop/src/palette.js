// Palette rows (F9): "Draw a card", one "Draw from <deck name>" per drawable deck, "Open decks".
// Rows register at load and again whenever the deck list may have changed (a switch, a save).
import { PALETTE_AREA, queryClient } from '@hermes/plugin-sdk'

import { api } from './api.js'
import { ID, log, qk } from './core.js'
import { drawableDecks } from './queries.js'
import { drawCard, openPage } from './state.js'

const KEYWORDS = ['unblockbruecke', 'unblock', 'card', 'cards', 'stuck', 'oblique']
export const DRAW_ACTION = `${ID}.draw`

let ctxRef = null
let fixed = []
let perDeck = []
let pending = null

export function registerPalette(ctx) {
  ctxRef = ctx
  fixed = [
    ctx.register({ id: 'palette-draw', area: PALETTE_AREA, data: { id: `${ID}.palette.draw`, label: 'Draw a card', action: DRAW_ACTION, keywords: KEYWORDS, run: () => drawCard() } }),
    ctx.register({ id: 'palette-decks', area: PALETTE_AREA, data: { id: `${ID}.palette.decks`, label: 'Open decks', keywords: [...KEYWORDS, 'deck', 'edit', 'import', 'export'], run: () => openPage('decks') } }),
  ]
  return refreshPalette()
}

/** Re-read GET /decks and replace the per-deck rows. Failures keep the rows that are there. */
export function refreshPalette() {
  if (!ctxRef) return Promise.resolve()
  if (pending) return pending
  pending = (async () => {
    try {
      const out = await api.decks()
      queryClient.setQueryData(qk('decks'), out)
      const decks = drawableDecks(out.decks)
      perDeck.forEach(d => d())
      perDeck = decks.map(d => ctxRef.register({ id: `palette-draw-${d.deck}`, area: PALETTE_AREA,
        data: { id: `${ID}.palette.draw.${d.deck}`, label: `Draw from ${d.name}`, keywords: [...KEYWORDS, d.deck, d.area || ''].filter(Boolean), detail: () => `${d.cards} cards`, run: () => drawCard({ deck: d.deck }) } }))
    } catch (error) {
      log('palette rows not refreshed', error.message)
    } finally {
      pending = null
    }
  })()
  return pending
}

export function disposePalette() {
  fixed.forEach(d => d())
  perDeck.forEach(d => d())
  fixed = []
  perDeck = []
  ctxRef = null
}
