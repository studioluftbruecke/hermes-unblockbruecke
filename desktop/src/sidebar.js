// The sidebar row "Unblockbrücke" (F17, PLAN constraint 14, Q6). The SDK hands plugin.js no config_schema
// values, so the row follows the plugin's own GET /settings answer: registered while show_in_sidebar
// is true, its disposer called when it turns false. Re-read when the window gains focus and every
// 60 s through ctx.setInterval (the one hand-rolled poll; every other read is React Query). A failed
// read keeps the row as it is, so a short outage does not make it flicker.
import { queryClient, SIDEBAR_NAV_AREA } from '@hermes/plugin-sdk'

import { api } from './api.js'
import { log, PATH, qk } from './core.js'

export const SIDEBAR_POLL_MS = 60000
let disposeRow = null
let ctxRef = null

export const sidebarShown = () => !!disposeRow

function apply(show) {
  if (show && !disposeRow) disposeRow = ctxRef.register({ id: 'nav', area: SIDEBAR_NAV_AREA, data: { path: PATH, label: 'Unblockbrücke', codicon: 'layers' } })
  else if (!show && disposeRow) {
    disposeRow()
    disposeRow = null
  }
}

export async function readSidebarSetting() {
  if (!ctxRef) return null
  try {
    const out = await api.settings()
    queryClient.setQueryData(qk('settings'), out)
    const show = !!(out && out.settings && out.settings.show_in_sidebar === true)
    apply(show)
    return show
  } catch (error) {
    log('settings read failed; sidebar row unchanged', error.message)
    return null
  }
}

export function startSidebar(ctx) {
  ctxRef = ctx
  readSidebarSetting()
  if (typeof ctx.setInterval === 'function') ctx.setInterval(readSidebarSetting, SIDEBAR_POLL_MS)
  if (typeof ctx.addEventListener === 'function' && typeof window !== 'undefined') ctx.addEventListener(window, 'focus', () => readSidebarSetting())
}

export function stopSidebar() {
  if (disposeRow) disposeRow()
  disposeRow = null
  ctxRef = null
}
