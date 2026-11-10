// The shared React Query reads every surface uses (Desktop's one QueryClient: cache, dedupe,
// refetchInterval, invalidation on writes). No hand-rolled poll loops here.
import { host, queryClient, useQuery, useValue } from '@hermes/plugin-sdk'

import { api } from './api.js'
import { ID, qk } from './core.js'

export const useProfile = () => useValue(host.state.profile) || 'default'

const key = (profile, ...rest) => [ID, profile, ...rest]

export function useDecks() {
  const profile = useProfile()
  return useQuery({ queryKey: key(profile, 'decks'), queryFn: api.decks, staleTime: 30000, retry: false })
}

export function useDeck(slug, opts = {}) {
  const profile = useProfile()
  return useQuery({ queryKey: key(profile, 'deck', slug), queryFn: () => api.deck(slug), enabled: !!slug && opts.enabled !== false, staleTime: opts.staleTime ?? 30000, retry: false })
}

export function useToday() {
  const profile = useProfile()
  return useQuery({ queryKey: key(profile, 'today'), queryFn: api.today, staleTime: 600000, refetchInterval: 900000, retry: false })
}

export function useJournal({ by = '', limit = 50 } = {}) {
  const profile = useProfile()
  return useQuery({ queryKey: key(profile, 'journal', by || 'all', limit), queryFn: () => api.journal({ by, limit }), staleTime: 10000, retry: false })
}

export function useSettings() {
  const profile = useProfile()
  return useQuery({ queryKey: key(profile, 'settings'), queryFn: api.settings, staleTime: 30000, retry: false })
}

export function useVersions(slug) {
  const profile = useProfile()
  return useQuery({ queryKey: key(profile, 'versions', slug), queryFn: () => api.versions(slug), enabled: !!slug, retry: false })
}

/** Q3: the newest auto-draw in one chat, polled every 5 s while Desktop is in front. */
export function useAutoDraw(sessionId) {
  const profile = useProfile()
  return useQuery({
    queryKey: key(profile, 'journal', 'auto', sessionId || '-'),
    queryFn: () => api.journal({ by: 'auto', session: sessionId, limit: 1 }),
    enabled: !!sessionId,
    refetchInterval: 5000,
    refetchIntervalInBackground: false,
    retry: false,
  })
}

/** After a deck write: every deck read, the palette rows and the versions list. */
export function invalidateDecks() {
  return queryClient.invalidateQueries({ queryKey: qk() })
}

export const drawableDecks = decks => (decks || []).filter(d => !d.shadowed_by && d.switch && d.switch.draw)
export const visibleDecks = decks => (decks || []).filter(d => !d.shadowed_by)
