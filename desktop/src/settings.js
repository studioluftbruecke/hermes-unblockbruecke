// The plugin's settings page (Settings ▸ Plugins ▸ UnblockBrücke ▸ Decks and learning): the deck
// switches and the learning reset. Auto-draw, its threshold and decks, card of the day, learning and
// "Show in sidebar" are the plugin's config_schema keys, which Desktop renders in its own form for
// this plugin; this page shows their current values and points there. It never writes config.yaml.
import { atom, host, pluginSettingsHref, Switch, useValue } from '@hermes/plugin-sdk'
import { jsx } from 'react/jsx-runtime'

import { api } from './api.js'
import { deckNames, ID, SETTINGS_PATH, toast } from './core.js'
import { ResetLearning } from './journal.js'
import { ConnectionNote } from './page.js'
import { refreshPalette } from './palette.js'
import { invalidateDecks, useDecks, useSettings, visibleDecks } from './queries.js'
import { openPage } from './state.js'
import { Btn, h, Mark, SOURCE_LABEL } from './ui.js'

const yes = v => (v ? 'on' : 'off')

export function SettingsPage() {
  const decks = useDecks()
  const settings = useSettings()
  const s = settings.data && settings.data.settings
  const list = visibleDecks(decks.data && decks.data.decks)
  const toggle = async (d, key, value) => {
    try {
      await api.setSwitch(d.deck, { [key]: value })
      invalidateDecks()
      refreshPalette()
    } catch (error) {
      toast(`Could not switch ${d.name}: ${error.message}`, 'warning')
    }
  }
  return h('div', { className: 'ubk col', style: { gap: 14, padding: 4, maxWidth: 820 }, 'data-ubk': 'settings' },
    h(ConnectionNote, { error: decks.error || settings.error }),
    h('div', { className: 'panel', style: { padding: '12px 14px' } },
      h('h2', null, 'Plugin settings'),
      h('p', { className: 'note', style: { marginTop: 4 } }, `Auto-draw, card of the day, learning and Show in sidebar live in plugin settings: ${SETTINGS_PATH}.`),
      h('p', { className: 'note' }, 'Changes there show here within a minute.'),
      s ? h('dl', { className: 'kv small', style: { marginTop: 8, gridTemplateColumns: '130px minmax(0, 1fr)' }, 'data-ubk': 'current-settings' },
        h('dt', null, 'Auto-draw'), h('dd', null, yes(s.autodraw)),
        h('dt', null, 'When it draws'), h('dd', null, `after ${s.autodraw_threshold} failed calls in a row, at most ${s.autodraw_per_turn} per turn`),
        h('dt', null, 'Auto-draw decks'), h('dd', null, deckNames(s.autodraw_decks, decks.data && decks.data.decks).join(', ') || 'none'),
        h('dt', null, 'Card of the day'), h('dd', null, yes(s.card_of_day)),
        h('dt', null, 'Learning'), h('dd', null, yes(s.learning)),
        h('dt', null, 'Show in sidebar'), h('dd', null, yes(s.show_in_sidebar))) : null,
      h('div', { className: 'row', style: { marginTop: 8 } },
        h(Btn, { sm: true, onClick: () => host.navigate(pluginSettingsHref(ID)) }, 'Open plugin settings'),
        h(Btn, { sm: true, onClick: () => openPage('decks') }, 'Open decks'))),
    h('div', { className: 'panel' },
      h('div', { className: 'sheethead' }, h('h2', null, 'Deck switches'), h('span', { className: 'grow' }), h('span', { className: 'note' }, 'Draw: at the table, the chip and the palette. Auto-draw: Hermes may draw from it when stuck.')),
      list.length ? h('table', { className: 'tbl', 'data-ubk': 'switches' },
        h('thead', null, h('tr', null, h('th', null, 'Deck'), h('th', null, 'Source'), h('th', { className: 'num' }, 'Cards'), h('th', null, 'Draw'), h('th', null, 'Auto-draw'))),
        h('tbody', null, list.map(d => jsx('tr', { children: [
          jsx('td', { children: h('span', { className: 'who' }, h(Mark, { mark: d.mark }), h('span', { dir: 'auto' }, d.name)) }, 'n'),
          jsx('td', { children: SOURCE_LABEL[d.source] || d.source }, 's'),
          jsx('td', { className: 'num', children: String(d.cards) }, 'c'),
          jsx('td', { children: jsx(Switch, { size: 'xs', checked: !!(d.switch && d.switch.draw), onCheckedChange: v => toggle(d, 'draw', v), 'aria-label': `Draw from ${d.name}` }) }, 'd'),
          jsx('td', { children: jsx(Switch, { size: 'xs', checked: !!(d.switch && d.switch.auto), onCheckedChange: v => toggle(d, 'auto', v), 'aria-label': `Auto-draw from ${d.name}` }) }, 'a'),
        ] }, d.deck)))) : h('p', { className: 'note', style: { padding: 14 } }, decks.isLoading ? 'Loading the decks…' : 'No decks loaded.')),
    h('div', { className: 'panel setrow' },
      h('div', { className: 'col', style: { gap: 2 } }, h('strong', null, 'Learning'),
        h('span', { className: 'note' }, 'Cards you rated as helpful come up a little more often; every card keeps a floor. Reset starts the weights again; the journal stays.')),
      h(ResetLearning, { learning: s ? s.learning : undefined })),
    h(TwoPlaceNote, null))
}

// Desktop loads this file from the computer it runs on, never from a remote Hermes, so an update on the
// server leaves this half behind. host.state.connectionId is 'local' for this computer's own Hermes
// (Desktop's LOCAL_CONNECTION_ID, never given to a remote source); any other value, null or a Desktop
// without the field shows the line, because a missed update costs more than one line.
const NO_CONNECTION = atom(null)
const TWO_PLACE_TIP = 'No Hermes on this computer: Capabilities → Plugins → Install from Git with this plugin\'s repository, Force reinstall.'

function TwoPlaceNote() {
  const id = useValue((host.state && host.state.connectionId) || NO_CONNECTION)
  if (id === 'local') return null
  return h('p', { className: 'note', title: TWO_PLACE_TIP, 'data-ubk': 'two-place' },
    'Hermes on another computer? Update this plugin on both. Here: ', h('code', null, `hermes plugins update ${ID}`), ', then Rescan.')
}
