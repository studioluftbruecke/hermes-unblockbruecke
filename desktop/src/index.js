/**
 * Unblockbrücke, the Desktop half: the Unblockbrücke page (table, decks, journal) and its sidebar row
 * (the shared sidebar-row module: a show switch and a position on the settings page, kept per Desktop),
 * the Draw button in the status bar behind "Show in status bar", palette rows, the rebindable "Draw a
 * card" shortcut, the `card` transcript directive, and the plugin's settings page. Source of
 * desktop/plugin.js, built by desktop/build/build.mjs.
 *
 * Desktop evaluates every plugin.js at start, so nothing heavy runs at module top level; register()
 * adds the stylesheet and the contributions and starts two small reads (decks for the palette rows,
 * settings for the Draw button and the sidebar row's one-time seed).
 */
import { KEYBINDS_AREA, ROUTES_AREA, TRANSCRIPT_DIRECTIVE_AREA } from '@hermes/plugin-sdk'
import { jsx } from 'react/jsx-runtime'

import { ID, log, NAME, PATH, setCtx } from './core.js'
import { CardDirective } from './directive.js'
import { CardsPage } from './page.js'
import { DRAW_ACTION, disposePalette, registerPalette } from './palette.js'
import { SettingsPage } from './settings.js'
import { drawCard } from './state.js'
import { installStyle } from './style.js'
import { startVisibility, stopVisibility } from './visibility.js'

export const DRAW_DEFAULT_KEYS = ['mod+alt+u']

export default {
  id: ID,
  name: NAME,
  description: 'Decks of short original cards that get humans and agents unstuck: a Draw button in the status bar, a card table, your own decks, a journal of what helped.',
  register(ctx) {
    setCtx(ctx)
    ctx.onDispose(installStyle())
    ctx.register({ id: 'page', area: ROUTES_AREA, title: 'Unblockbrücke', data: { path: PATH }, render: () => jsx(CardsPage, {}) })
    ctx.register({ id: 'directive-card', area: TRANSCRIPT_DIRECTIVE_AREA, data: { name: 'card', render: props => jsx(CardDirective, props) } })
    ctx.register({ id: 'draw-key', area: KEYBINDS_AREA, data: { id: DRAW_ACTION, label: 'Unblockbrücke: Draw a card', category: 'view', defaults: DRAW_DEFAULT_KEYS, run: () => drawCard() } })
    if (typeof ctx.registerSettingsPage === 'function') {
      ctx.registerSettingsPage({ id: 'cards', title: 'Unblockbrücke', icon: 'layers', render: () => jsx(SettingsPage, {}) })
    }
    registerPalette(ctx)
    startVisibility(ctx)
    ctx.onDispose(() => {
      disposePalette()
      stopVisibility()
    })
    log('registered page, card directive, keybind mod+alt+u, settings page, palette rows, sidebar row; Draw button follows show_in_statusbar')
  },
}
