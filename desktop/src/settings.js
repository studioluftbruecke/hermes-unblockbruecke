// The plugin's settings page (Settings ▸ Plugins ▸ Unblockbrücke). It stays registered because Desktop
// names the Settings ▸ Plugins entry from it, and it is a pointer: one button that opens the page, the
// sidebar row's switch and position (the shared SidebarSection, kept per Desktop in ctx.storage), and
// the two-place update note. Everything else lives on the page; Desktop's own form under Agent settings
// writes the same keys as the Hermes tab.
import { atom, host, useValue } from '@hermes/plugin-sdk'
import { jsx } from 'react/jsx-runtime'

import { ID, NAME } from './core.js'
import { SidebarSection } from './sidebar-row.js'
import { openPage } from './state.js'
import { Btn, h } from './ui.js'
import { SIDEBAR_SDK, sidebarRow } from './visibility.js'

export function SettingsPage() {
  const row = sidebarRow()
  return h('div', { className: 'ubk col', style: { gap: 14, padding: 4, maxWidth: 820 }, 'data-ubk': 'settings' },
    h('div', { className: 'row' }, h(Btn, { pri: true, onClick: () => openPage() }, `Open ${NAME}`)),
    row ? jsx(SidebarSection, { row, sdk: SIDEBAR_SDK }) : null,
    h(TwoPlaceNote, null))
}

// Desktop loads this file from the computer it runs on, never from a remote Hermes, so an update on the
// server leaves this half behind. host.state.connectionId is 'local' for this computer's own Hermes
// (Desktop's LOCAL_CONNECTION_ID, never given to a remote source); any other value, null or a Desktop
// without the field shows the line, because a missed update costs more than one line.
const NO_CONNECTION = atom(null)
const TWO_PLACE_TIP = 'No Hermes on this computer: Capabilities → Plugins → Install from Git with this plugin\'s repository, Force reinstall.'

export function TwoPlaceNote() {
  const id = useValue((host.state && host.state.connectionId) || NO_CONNECTION)
  if (id === 'local') return null
  return h('p', { className: 'note', title: TWO_PLACE_TIP, 'data-ubk': 'two-place' },
    'Hermes on another computer? Update this plugin on both. Here: ', h('code', null, `hermes plugins update ${ID}`), ', then Rescan.')
}
