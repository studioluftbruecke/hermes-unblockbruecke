// The Hermes tab: one switch "Hermes draws when stuck" with one sentence and an example
// card (front and back), how many failed calls bring a card, the switch of each deck that has cards
// written for Hermes, and what Hermes drew lately with where the turn ran and what the next call did.
// The switch and the count save through POST /setting (a fixed list of keys); Desktop's own plugin
// settings form writes the same keys, and both read them live.
import * as SDK from '@hermes/plugin-sdk'
import { useValue } from '@hermes/plugin-sdk'
import { jsx } from 'react/jsx-runtime'

import { api } from './api.js'
import { qk, toast, whenLocal } from './core.js'
import { viewFromDeck } from './directive.js'
import { nextFact, RateButtons, whereText } from './history.js'
import { refreshPalette } from './palette.js'
import { invalidateDecks, settingsOf, useDeck, useJournal, useSettings, visibleDecks } from './queries.js'
import { $rated } from './state.js'
import { Card, h, hk } from './ui.js'

export const THRESHOLDS = [2, 3, 4, 5, 6]
const EXAMPLE_ID = 'ag-03'

/** The sentence under the switch, for a count of failed calls (n of the last n + 2). */
export const hermesSentence = n => `After ${n} failed tool calls out of the last ${n + 2}, Hermes gets one card with a next move.`

/** One saved setting. `queryClient` gets the answer (the same body as GET /settings) at once. */
export async function saveSetting(key, value) {
  try {
    const out = await api.setting(key, value)
    if (out && out.settings) SDK.queryClient.setQueryData(qk('settings'), out)
    else SDK.queryClient.invalidateQueries({ queryKey: qk('settings') })
    return true
  } catch (error) {
    toast(`Could not save: ${error.message}`, 'warning')
    SDK.queryClient.invalidateQueries({ queryKey: qk('settings') })
    return false
  }
}

/** Desktop's Switch, or a plain switch button on a Desktop without it. */
export function Toggle({ checked, onChange, label, disabled }) {
  if (SDK.Switch) return jsx(SDK.Switch, { checked: !!checked, onCheckedChange: onChange, 'aria-label': label, disabled })
  return h('button', { type: 'button', role: 'switch', className: 'switch', 'aria-checked': !!checked, 'aria-label': label, disabled, onClick: () => onChange(!checked) })
}

function Count({ value, onChange, disabled }) {
  const options = THRESHOLDS.map(n => ({ id: String(n), label: String(n) }))
  if (SDK.SegmentedControl) return h('div', { role: 'group', 'aria-label': 'Failed calls before a card' }, jsx(SDK.SegmentedControl, { options, value: String(value), onChange: id => onChange(Number(id)), disabled }))
  return h('div', { className: 'seg', role: 'group', 'aria-label': 'Failed calls before a card' },
    options.map(o => hk(o.id, 'button', { type: 'button', 'aria-pressed': String(value) === o.id, disabled, onClick: () => onChange(Number(o.id)) }, o.label)))
}

/** The example card under the switch: `hermes.example` from GET /settings, else
 *  an `auto` card read from the deck (a backend without the field). */
function Example({ slug, example }) {
  const q = useDeck(slug, { staleTime: 300000, enabled: !example })
  if (example) return h('div', { className: 'examples', 'data-ubk': 'example' }, h(Card, { card: example, face: 'front', width: 160, size: 'xs' }), h(Card, { card: example, face: 'rear', width: 160, size: 'xs' }))
  const deck = q.data && q.data.deck
  if (!deck) return null
  const cards = deck.cards || []
  const pick = cards.find(c => c.id === EXAMPLE_ID) || cards.find(c => (c.tags || []).includes('auto')) || cards[0]
  const view = pick ? viewFromDeck(deck, pick.id, 'human') : null
  if (!view) return null
  return h('div', { className: 'examples', 'data-ubk': 'example' }, h(Card, { card: view, face: 'front', width: 160, size: 'xs' }), h(Card, { card: view, face: 'rear', width: 160, size: 'xs' }))
}

function Row({ title, sub, control, below, off, ubk }) {
  return h('div', { className: `d-row${off ? ' off' : ''}`, 'data-ubk': ubk },
    h('div', null, h('div', { className: 'tt' }, title), sub ? h('div', { className: 'ds' }, sub) : null),
    control,
    below ? h('div', { className: 'below' }, below) : null)
}

function Lately() {
  // by=hermes: Hermes' draws, asked for in a chat or drawn when stuck.
  const q = useJournal({ by: 'hermes', limit: 8 })
  const rated = useValue($rated)
  const draws = (q.data && q.data.draws) || []
  return h('section', { className: 'log', 'data-ubk': 'lately' },
    h('h2', { className: 'sec' }, 'What Hermes drew lately'),
    q.isLoading ? h('p', { className: 'note' }, 'Loading…') : null,
    q.error ? h('p', { className: 'note' }, `The list did not load: ${q.error.message}`) : null,
    q.data && !draws.length ? h('p', { className: 'note' }, 'Nothing yet. When Hermes draws a card, it shows up here, also for runs nobody watched.') : null,
    draws.length ? h('ul', { className: 'loglist' }, draws.map((d, i) => {
      const v = d.view
      const next = nextFact(d)
      const rating = rated[d.draw_id] || d.rating
      // The newest draw asks once; older rows show their rating, if any.
      const ask = !rating && i === 0
      return hk(d.draw_id, 'li', { 'data-draw': d.draw_id },
        h('span', { className: 'ln', dir: 'auto', title: v ? v.agent : '' }, v ? v.human : d.card),
        h('span', { className: 'faint' }, whereText(d)),
        h('span', { className: `res ${next.tone}` }, next.text),
        h('span', { className: 'faint' }, whenLocal(d.at)),
        rating ? h('span', { className: 'badge' }, rating === 'helped' ? 'Helped' : 'Not this time') : ask ? h(RateButtons, { drawId: d.draw_id, label: v ? v.human : d.card }) : h('span', null))
    })) : null)
}

export function HermesView({ decksData }) {
  const settings = useSettings()
  const s = settingsOf(settings.data)
  const decks = visibleDecks(decksData && decksData.decks)
  // Only decks with cards written for Hermes get a switch: Hermes draws `auto` cards only.
  const forHermes = decks.filter(d => d.auto_cards > 0)
  const on = !!(s && s.autodraw)
  const threshold = (s && s.autodraw_threshold) || 3
  const toggleDeck = async (d, value) => {
    try {
      await api.setSwitch(d.deck, { auto: value })
      invalidateDecks()
      refreshPalette()
    } catch (error) {
      toast(`Could not switch ${d.name}: ${error.message}`, 'warning')
    }
  }
  const example = forHermes[0] ? forHermes[0].deck : 'agent-unblock'
  return h('div', { className: 'hset', 'data-ubk': 'hermes' },
    h(Row, { ubk: 'autodraw', title: 'Hermes draws when stuck', sub: hermesSentence(threshold),
      control: h(Toggle, { checked: on, label: 'Hermes draws when stuck', disabled: !s, onChange: v => saveSetting('autodraw', v) }),
      below: h(Example, { slug: example, example: settings.data && settings.data.hermes ? settings.data.hermes.example : null }) }),
    h(Row, { ubk: 'threshold', off: !on, title: 'Failed calls before a card', sub: 'Counted over the last few calls of a turn.',
      control: h(Count, { value: threshold, disabled: !s, onChange: n => saveSetting('autodraw_threshold', n) }) }),
    forHermes.map(d => hk(d.deck, Row, { ubk: `deck-${d.deck}`, off: !on, title: `${d.name} deck`, sub: `${d.auto_cards} cards written for Hermes.${forHermes.length === 1 ? ' The other decks have none yet.' : ''}`,
      control: h(Toggle, { checked: !!(d.switch && d.switch.auto), label: `Hermes may use the ${d.name} deck`, onChange: v => toggleDeck(d, v) }) })),
    h(Lately, null))
}
