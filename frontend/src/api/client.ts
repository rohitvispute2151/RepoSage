import createClient from 'openapi-fetch'
import type { paths } from './schema'
import { ApiError, errorFromStatus, networkError } from './errors'
import { useSessionStore } from '@/stores/session'

export const API_BASE: string = import.meta.env.VITE_API_BASE ?? ''

export function createApiClient(getApiKey: () => string) {
  const client = createClient<paths>({
    baseUrl: API_BASE,
    // Resolve fetch lazily so test doubles (MSW) installed after module load are honoured.
    fetch: (req) => globalThis.fetch(req),
  })
  client.use({
    onRequest({ request }) {
      const key = getApiKey()
      if (key) request.headers.set('X-API-Key', key)
      return request
    },
  })
  return client
}

export const api = createApiClient(() => useSessionStore().apiKey)

type Result<T> = { data?: T; error?: unknown; response: Response }

/** Unwraps an openapi-fetch result, mapping failures onto ApiError. */
export async function unwrap<T>(call: Promise<Result<T>>): Promise<T> {
  let res: Result<T>
  try {
    res = await call
  } catch (e) {
    throw networkError(e)
  }
  if (res.response.ok && res.data !== undefined) return res.data
  if (res.response.ok) return undefined as T
  throw errorFromStatus(res.response.status, res.error)
}

export { ApiError }
