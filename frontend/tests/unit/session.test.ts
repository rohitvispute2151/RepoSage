import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useSessionStore } from '@/stores/session'
import { createApiClient } from '@/api/client'

describe('default API key', () => {
  beforeEach(() => { localStorage.clear(); setActivePinia(createPinia()) })

  it('is sent by default in dev, without the user entering anything', () => {
    expect(useSessionStore().apiKey).toBe('reposage-dev-key')
  })
  it('a stored key wins, and an explicitly cleared key stays empty', () => {
    localStorage.setItem('reposage.apiKey', 'mine')
    expect(useSessionStore().apiKey).toBe('mine')
    setActivePinia(createPinia())
    localStorage.setItem('reposage.apiKey', '')
    expect(useSessionStore().apiKey).toBe('')
  })
  it('the client puts it on the request as X-API-Key', async () => {
    let seen: string | null = null
    const c = createApiClient(() => useSessionStore().apiKey)
    const orig = globalThis.fetch
    globalThis.fetch = (async (req: Request) => { seen = req.headers.get('x-api-key'); return new Response('{}', { headers: { 'content-type': 'application/json' } }) }) as unknown as typeof fetch
    try { await c.GET('/v1/repos/{snapshot_id}', { params: { path: { snapshot_id: 'x' } } }) } finally { globalThis.fetch = orig }
    expect(seen).toBe('reposage-dev-key')
  })
})
