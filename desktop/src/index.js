/**
 * Unblockbrücke, the Desktop half: the Unblockbrücke page (table, decks, journal) and its sidebar row
 * behind "Show in sidebar", the status-bar chip (card of the day, "Hermes drew <id>"), palette rows,
 * the rebindable "Draw a card" shortcut, the `card` transcript directive, and the plugin's settings
 * page. Source of desktop/plugin.js, built by desktop/build/build.mjs.
 *
 * Desktop evaluates every plugin.js at start, so nothing heavy runs at module top level; register()
 * adds the stylesheet and the contributions and starts two small reads (decks for the palette rows,
 * settings for the sidebar row).
 */
import { KEYBINDS_AREA, ROUTES_AREA, STATUSBAR_AREAS, TRANSCRIPT_DIRECTIVE_AREA } from '@hermes/plugin-sdk'
import { jsx } from 'react/jsx-runtime'

import { Chip } from './chip.js'
import { ID, log, NAME, PATH, setCtx } from './core.js'
import { CardDirective } from './directive.js'
import { CardsPage } from './page.js'
import { DRAW_ACTION, disposePalette, registerPalette } from './palette.js'
import { SettingsPage } from './settings.js'
import { startSidebar, stopSidebar } from './sidebar.js'
import { drawCard, shortcutDeck } from './state.js'
import { installStyle } from './style.js'

export const DRAW_DEFAULT_KEYS = ['mod+alt+u']

export default {
  id: ID,
  name: NAME,
  description: 'Decks of short original cards that get humans and agents unstuck: a card table, your own decks, a journal of what helped, the card of the day.',
  register(ctx) {
    setCtx(ctx)
    ctx.onDispose(installStyle())
    ctx.register({ id: 'page', area: ROUTES_AREA, title: 'Unblockbrücke', data: { path: PATH }, render: () => jsx(CardsPage, {}) })
    ctx.register({ id: 'chip', area: STATUSBAR_AREAS.right, render: () => jsx(Chip, {}) })
    ctx.register({ id: 'directive-card', area: TRANSCRIPT_DIRECTIVE_AREA, data: { name: 'card', render: props => jsx(CardDirective, props) } })
    ctx.register({ id: 'draw-key', area: KEYBINDS_AREA, data: { id: DRAW_ACTION, label: 'Unblockbrücke: Draw a card', category: 'view', defaults: DRAW_DEFAULT_KEYS, run: async () => drawCard({ deck: await shortcutDeck() }) } })
    if (typeof ctx.registerSettingsPage === 'function') {
      ctx.registerSettingsPage({ id: 'cards', title: 'Unblockbrücke', icon: 'layers', render: () => jsx(SettingsPage, {}) })
    }
    registerPalette(ctx)
    startSidebar(ctx)
    ctx.onDispose(() => {
      disposePalette()
      stopSidebar()
    })
    log('registered page, chip, card directive, keybind mod+alt+u, settings page, palette rows; sidebar row follows show_in_sidebar')
  },
}
