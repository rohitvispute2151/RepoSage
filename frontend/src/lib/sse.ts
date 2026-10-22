/** Minimal fetch-based SSE client. EventSource cannot send the X-API-Key header, so we parse the stream ourselves. */

export interface RawSse {
  id: string | null
  event: string
  data: string
}

export type ConnectionState =
  | { phase: 'idle' }
  | { phase: 'connecting' }
  | { phase: 'open' }
  | { phase: 'reconnecting'; attempt: number; delayMs: number; reason: string }
  | { phase: 'closed' }
  | { phase: 'failed'; reason: string; fatal: boolean; status: number | null }

export function createSseParser(onMessage: (m: RawSse) => void) {
  let buffer = ''
  let id: string | null = null
  let event = ''
  let data: string[] = []

  const dispatch = () => {
    if (data.length || event) onMessage({ id, event: event || 'message', data: data.join('\n') })
    event = ''
    data = []
    id = null // per-event ids: the server's id-less `done` must not inherit the previous id (and be deduped away)
  }

  return {
    push(chunk: string) {
      buffer += chunk
      let idx: number
      // Lines end in \n, \r\n or \r; hold back a trailing \r in case \n follows in the next chunk.
      while ((idx = buffer.search(/\r\n|\n|\r(?!$)/)) !== -1) {
        const line = buffer.slice(0, idx)
        buffer = buffer.slice(buffer[idx] === '\r' && buffer[idx + 1] === '\n' ? idx + 2 : idx + 1)
        if (line === '') dispatch()
        else if (line.startsWith(':')) continue
        else {
          const c = line.indexOf(':')
          const field = c === -1 ? line : line.slice(0, c)
          let value = c === -1 ? '' : line.slice(c + 1)
          if (value.startsWith(' ')) value = value.slice(1)
          if (field === 'id') id = value
          else if (field === 'event') event = value
          else if (field === 'data') data.push(value)
        }
      }
    },
  }
}

export interface RunSseOptions {
  url: string
  headers: () => Record<string, string>
  signal: AbortSignal
  onMessage: (m: RawSse) => void
  onState: (s: ConnectionState) => void
  /** Highest sequence already consumed; sent as Last-Event-ID. */
  getLastEventId: () => number
  fetchImpl?: (url: string, init: RequestInit) => Promise<Response>
  sleep?: (ms: number, signal: AbortSignal) => Promise<void>
  maxAttempts?: number
  baseDelayMs?: number
  maxDelayMs?: number
}

const defaultSleep = (ms: number, signal: AbortSignal) =>
  new Promise<void>((resolve) => {
    const t = setTimeout(resolve, ms)
    signal.addEventListener('abort', () => { clearTimeout(t); resolve() }, { once: true })
  })

/** Streams until the server sends `done`, the signal aborts, or retries are exhausted. */
export async function runSse(o: RunSseOptions): Promise<void> {
  const doFetch = o.fetchImpl ?? ((url: string, init: RequestInit) => globalThis.fetch(url, init))
  const sleep = o.sleep ?? defaultSleep
  const maxAttempts = o.maxAttempts ?? 6
  const base = o.baseDelayMs ?? 1000
  const cap = o.maxDelayMs ?? 8000
  let attempt = 0
  let reason = ''

  while (!o.signal.aborted) {
    if (attempt === 0) o.onState({ phase: 'connecting' })
    let sawDone = false
    try {
      const headers: Record<string, string> = { Accept: 'text/event-stream', ...o.headers() }
      const last = o.getLastEventId()
      if (last > 0) headers['Last-Event-ID'] = String(last)
      const res = await doFetch(o.url, { headers, signal: o.signal })
      if (!res.ok || !res.body) {
        const fatal = [401, 403, 404].includes(res.status)
        if (fatal) {
          o.onState({ phase: 'failed', reason: `Stream rejected (HTTP ${res.status})`, fatal: true, status: res.status })
          return
        }
        throw new Error(`HTTP ${res.status}`)
      }
      o.onState({ phase: 'open' })
      const parser = createSseParser((m) => {
        if (m.event === 'done') sawDone = true
        o.onMessage(m)
      })
      const reader = res.body.pipeThrough(new TextDecoderStream()).getReader()
      for (;;) {
        const { value, done } = await reader.read()
        if (done) break
        if (value) {
          attempt = 0 // healthy traffic resets the backoff
          parser.push(value)
        }
        if (sawDone) { await reader.cancel(); break }
      }
      if (sawDone) {
        o.onState({ phase: 'closed' })
        return
      }
      reason = 'stream ended before the task finished'
    } catch (e) {
      if (o.signal.aborted) return
      reason = e instanceof Error ? e.message : 'connection lost'
    }

    attempt += 1
    if (attempt > maxAttempts) {
      o.onState({ phase: 'failed', reason: `Gave up after ${maxAttempts} reconnect attempts: ${reason}`, fatal: false, status: null })
      return
    }
    const delayMs = Math.min(cap, base * 2 ** (attempt - 1))
    o.onState({ phase: 'reconnecting', attempt, delayMs, reason })
    await sleep(delayMs, o.signal)
  }
}
