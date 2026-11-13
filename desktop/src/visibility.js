// What the plugin shows in Desktop's frame: the sidebar row "Unblockbrücke" and the Draw button in the
// status bar (show_in_statusbar, PLAN-v0.1.3 M3).
//
// The sidebar row comes from the shared module (./sidebar-row.js, experiments/sidebar-rows/PLAN.md): its
// show switch and position are kept per Desktop in ctx.storage 'sidebar' and set on the plugin's settings
// page. The config key show_in_sidebar is retired (D4). One-time seed (V5): with no stored choice the row
// shows at start, and the FIRST GET /settings answer is applied once (show = show_in_sidebar !== false)
// and stored, so a Desktop updated from 0.1.3 keeps a row its user had switched off hidden after that
// read. A choice stored before the answer arrives wins; an answer without the key stores the defaults.
// Later reads never touch the row.
//
// The Draw button still follows the plugin's own GET /settings answer: registered while its key is true
// and disposed when it turns false. The SDK hands plugin.js no config_schema values, so one read runs
// when the window gains focus and every 60 s through ctx.setInterval (the one hand-rolled poll; every
// other read is React Query). A failed read keeps the button as it is, so a short outage does not make
// it flicker. It starts from the last answer stored in ctx.storage (default on), so register() shows it
// at once and a user who turned it off sees no flash at start (RV6).
//
// The button is a status-bar *data* item that owns its slot through `render`: only such an item can set
// `toggleLabel`, which lists it in Desktop's right-click show/hide menu under that name (P-SB,
// experiments/unblockbruecke/v0.1.3/probe-statusbar.out). Desktop keeps the hidden list by `data.id`,
// which the plugin context does not prefix, so the id carries the plugin's name itself.
import { atom, Input, queryClient, SIDEBAR_NAV_AREA, STATUSBAR_AREAS, Switch, useValue } from '@hermes/plugin-sdk'
import { jsx, jsxs } from 'react/jsx-runtime'

import { api } from './api.js'
import { Boundary, Chip } from './chip.js'
import { ID, log, NAME, PATH, qk, storage } from './core.js'
import { startSidebarRow } from './sidebar-row.js'

export const POLL_MS = 60000
export const STATUSBAR_ITEM_ID = `${ID}.draw`
const STORED = 'show_in_statusbar'
const SIDEBAR_KEY = 'sidebar'

/** The SDK names the shared module and its settings block use (the module imports nothing itself). */
export const SIDEBAR_SDK = { SIDEBAR_NAV_AREA, Switch, Input, jsx, jsxs, atom, useValue }

let ctxRef = null
let disposeBar = null
let row = null
let seedPending = false

/** The sidebar row handle while the plugin is registered, else null (the settings page reads it). */
export const sidebarRow = () => row
export const sidebarShown = () => !!(row && row.prefs().show)
export const statusbarShown = () => !!disposeBar

const hasStoredChoice = () => {
  const stored = storage.get(SIDEBAR_KEY, null)
  return !!stored && typeof stored === 'object'
}

/** The one-time seed from the first GET /settings answer. Returns true when it stored the row's prefs. */
function seedRow(settings) {
  seedPending = false
  if (!row || hasStoredChoice()) return false
  row.setPrefs({ show: settings.show_in_sidebar !== false })
  // setPrefs stores nothing when nothing changed (shown, at the default position), so store here.
  storage.set(SIDEBAR_KEY, row.prefs())
  return true
}

function applyBar(show) {
  if (show && !disposeBar) {
    disposeBar = ctxRef.register({ id: 'statusbar', area: STATUSBAR_AREAS.right,
      data: { id: STATUSBAR_ITEM_ID, toggleLabel: NAME, render: () => jsx(Boundary, { children: jsx(Chip, {}) }) } })
  } else if (!show && disposeBar) {
    disposeBar()
    disposeBar = null
  }
}

/** Read GET /settings once: apply show_in_statusbar, and on the first answer seed the sidebar row.
 *  Returns {sidebar, statusbar, seeded}, or null after a failed read (nothing changed). A backend
 *  without show_in_statusbar (0.1.2) counts as on, its default. */
export async function readVisibility() {
  if (!ctxRef) return null
  try {
    const out = await api.settings()
    queryClient.setQueryData(qk('settings'), out)
    const s = (out && out.settings) || {}
    const statusbar = s.show_in_statusbar !== false
    const seeded = seedPending ? seedRow(s) : false
    applyBar(statusbar)
    storage.set(STORED, statusbar)
    return { sidebar: sidebarShown(), statusbar, seeded }
  } catch (error) {
    log('settings read failed; Draw button unchanged', error.message)
    return null
  }
}

export function startVisibility(ctx) {
  ctxRef = ctx
  seedPending = !hasStoredChoice()
  row = startSidebarRow(ctx, { brand: 'Unblockbrücke', path: PATH, codicon: 'copy', defaultPosition: 53, sdk: SIDEBAR_SDK })
  applyBar(storage.get(STORED, true) !== false)
  readVisibility()
  if (typeof ctx.setInterval === 'function') ctx.setInterval(readVisibility, POLL_MS)
  if (typeof ctx.addEventListener === 'function' && typeof window !== 'undefined') ctx.addEventListener(window, 'focus', () => readVisibility())
}

export function stopVisibility() {
  if (row) row.dispose()
  if (disposeBar) disposeBar()
  row = null
  disposeBar = null
  seedPending = false
  ctxRef = null
}
