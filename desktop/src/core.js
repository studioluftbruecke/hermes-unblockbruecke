// Unblockbrücke, Desktop half: the backend door, connection state and small shared helpers.
// Every call goes to this plugin's own routes (`ctx.rest`, `/api/plugins/unblockbruecke/...`) through
// api.js; nothing here reaches any other host (PLAN constraint 11: the Desktop is a renderer).
import { atom, host } from '@hermes/plugin-sdk'

export const ID = 'unblockbruecke'
export const NAME = 'Unblockbrücke'
export const PATH = '/unblockbruecke'
export const SCHEMA = 1

let pluginCtx = null
export const setCtx = ctx => {
  pluginCtx = ctx
}
export const getCtx = () => pluginCtx

export const log = (...args) => console.info(`[${ID}]`, ...args)

// 'unknown' until the first answer, 'ok' after one, 'offline' when Desktop cannot reach the backend,
// 'off' after 404 "Plugin not found" (the plugin is not on in this profile), 'schema' when the
// backend answers another schema or lacks a route (an older or newer plugin).
export const $connection = atom('unknown')

export const NOT_ON_TEXT = 'Unblockbrücke is off in this Hermes profile. Turn it on under Settings ▸ Plugins, then open this page again.'
export const OFFLINE_TEXT = 'Desktop cannot reach Hermes right now: check that Hermes is running, then try again.'
export const SCHEMA_TEXT = 'This Desktop page and the Unblockbrücke plugin in this profile do not match: update the plugin.'
// Said instead of a raw server answer ("Internal Server Error", FastAPI's detail list): what failed is
// in the caller's prefix, what to try is here.
export const SERVER_TEXT = 'Hermes answered with an error. Try again, and check the gateway log if it repeats.'
// Where the plugin's own settings live; every surface names them the same way.
export const SETTINGS_PATH = 'Settings ▸ Plugins ▸ Unblockbrücke'

/** The plain sentence for a refusal that is not the contract's: a hint the user can act on when the
 *  host refused the request (signed out, a file too large, a short `detail`), else SERVER_TEXT. */
function hostText(status, detail) {
  if (status === 401) return 'Not signed in to Hermes. Sign in again and retry.'
  if (status === 413) return 'File too large for Hermes to take. Try a smaller file.'
  const short = status < 500 && detail && detail.length <= 80 && !/[{}[\]<>]/.test(detail) ? detail.replace(/\.$/, '') : ''
  return short ? `Hermes answered: ${short}. Try again, and check the gateway log if it repeats.` : SERVER_TEXT
}

// ctx.rest rejects on HTTP >= 400 with "<status>: <body>" somewhere in the message (Electron adds a
// prefix). Recover the status and the JSON body; anything without a status is a network error.
export function restError(error) {
  const message = error && error.message ? String(error.message) : String(error)
  const found = message.match(/\b([1-5]\d\d): ([\s\S]*)$/)
  const status = found ? Number(found[1]) : error && error.statusCode ? Number(error.statusCode) : 0
  let body = null
  const raw = found ? found[2] : message
  const start = raw.indexOf('{')
  if (start >= 0) {
    try {
      body = JSON.parse(raw.slice(start))
    } catch {
      body = null
    }
  }
  const detail = body && typeof body.detail === 'string' ? body.detail : ''
  const notOn = status === 404 && /plugin not found/i.test(detail || (body && body.message) || raw)
  // FastAPI's own 404 for a path the backend does not serve: the plugin is older than this page.
  const missingRoute = status === 404 && !notOn && detail === 'Not Found' && !(body && body.error)
  // Only the contract's own refusals ({error, message}) reach the user word for word.
  const contract = body && typeof body.error === 'string' && typeof body.message === 'string' && body.message.trim()
  const out = new Error(notOn ? NOT_ON_TEXT : missingRoute ? SCHEMA_TEXT : contract ? body.message : status ? hostText(status, detail) : OFFLINE_TEXT)
  out.status = status
  out.body = body
  out.code = (body && body.error) || null
  out.network = !status
  out.notOn = notOn
  out.schema = missingRoute
  return out
}

export class SchemaError extends Error {
  constructor(got) {
    super(SCHEMA_TEXT)
    this.schema = true
    this.got = got
  }
}

export async function rest(path, opts) {
  if (!pluginCtx || typeof pluginCtx.rest !== 'function') throw new Error('ctx.rest is not available in this Desktop build')
  let out
  try {
    out = await pluginCtx.rest(path, { timeoutMs: 20000, ...(opts || {}) })
  } catch (error) {
    const err = restError(error)
    if (err.network) $connection.set('offline')
    else if (err.notOn) $connection.set('off')
    else if (err.schema || (err.body && err.body.schema !== undefined && err.body.schema !== SCHEMA)) $connection.set('schema')
    else if ($connection.get() !== 'ok') $connection.set('ok')
    log('rest', (opts && opts.method) || 'GET', path, 'failed', { status: err.status, code: err.code, message: err.message })
    throw err
  }
  if (out && typeof out === 'object' && out.schema !== undefined && out.schema !== SCHEMA) {
    $connection.set('schema')
    throw new SchemaError(out.schema)
  }
  if ($connection.get() !== 'ok') $connection.set('ok')
  return out
}

/** A client op id for writes: a repeat answers {duplicate: true} and changes nothing (contract §5). */
export function opId() {
  const c = globalThis.crypto
  if (c && typeof c.randomUUID === 'function') return c.randomUUID()
  return `op-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
}

/** The profile the gateway socket is bound to: the one whose backend `ctx.rest` reaches. */
export const profileNow = () => (host.state && host.state.profile ? host.state.profile.get() : null) || 'default'

export const qk = (...rest) => [ID, profileNow(), ...rest]

export const storage = {
  get: (key, fallback) => (pluginCtx && pluginCtx.storage ? pluginCtx.storage.get(key, fallback) : fallback),
  set: (key, value) => pluginCtx && pluginCtx.storage && pluginCtx.storage.set(key, value),
}

export function toast(message, kind = 'info') {
  try {
    host.notify({ kind, title: NAME, message })
  } catch (error) {
    log('notify failed', String(error))
  }
}

const pad2 = n => String(n).padStart(2, '0')
const dayOnly = x => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime()

function dayWord(d, now) {
  const diff = Math.round((dayOnly(now) - dayOnly(d)) / 86400000)
  if (diff === 0) return 'Today'
  if (diff === 1) return 'Yesterday'
  if (diff > 1 && diff < 7) return d.toLocaleDateString('en-GB', { weekday: 'short' })
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
}

/** "Today 14:12", "Yesterday 22:31", "Mon 16:44" or "3 Nov 09:05", in this computer's local time. */
export function whenLocal(iso, now = new Date()) {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return String(iso || '')
  return `${dayWord(d, now)} ${pad2(d.getHours())}:${pad2(d.getMinutes())}`
}

/** A calendar date ("2026-11-10") through the same words as whenLocal, without a time: "Today", "3 Nov". */
export function dayLocal(date, now = new Date()) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(date || ''))
  if (!m) return String(date || '')
  return dayWord(new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3])), now)
}

/** Characters as the backend counts them (code points, Python's len()), not UTF-16 units. */
export const charCount = text => [...String(text || '')].length

/** Deck names for slugs, from a GET /decks answer; a slug without a deck stays as it is. */
export const deckNames = (slugs, decks) => (slugs || []).map(s => ((decks || []).find(d => d.deck === s) || {}).name || s)

// Contract regexes (§1): deck slug and card id. The transcript directive and the page validate with them.
export const SLUG_RE = /^[a-z0-9-]{2,40}$/
export const CARD_ID_RE = /^[a-z]{2,4}-\d{2}$/
export const TAG_RE = /^[a-z][a-z0-9-]{1,20}$/

// The two built-in tags (contract §1); GET /decks/{slug} glossaries carry only the deck's own tags.
export const BUILTIN_TAGS = {
  human: 'Asks a person something; Hermes never draws it on its own when nobody is at the keyboard.',
  auto: 'Written for Hermes, for the moment right after several failed tool calls.',
}

export const isPagePath = () => {
  const hash = typeof window !== 'undefined' ? String(window.location.hash || '') : ''
  return hash === `#${PATH}` || hash.startsWith(`#${PATH}?`)
}
