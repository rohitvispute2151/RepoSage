import { describe, expect, it } from 'vitest'
import { createSseParser, runSse, type ConnectionState, type RawSse } from '@/lib/sse'

const collect = (chunks: string[]) => {
  const out: RawSse[] = []
  const p = createSseParser((m) => out.push(m))
  chunks.forEach((c) => p.push(c))
  return out
}

describe('SSE parser', () => {
  it('parses id/event/data and survives arbitrary chunk boundaries', () => {
    const wire = 'id: 7\nevent: node_started\ndata: {"node":"plan"}\n\n'
    for (let cut = 1; cut < wire.length; cut++) {
      expect(collect([wire.slice(0, cut), wire.slice(cut)])).toEqual([{ id: '7', event: 'node_started', data: '{"node":"plan"}' }])
    }
  })

  it('handles CRLF, comments and multi-line data', () => {
    expect(collect([': keepalive\r\nevent: x\r\ndata: a\r\ndata: b\r\n\r\n'])).toEqual([{ id: null, event: 'x', data: 'a\nb' }])
  })

  it('reports `done` without an id', () => {
    expect(collect(['event: done\ndata: {"status":"completed"}\n\n'])[0]).toMatchObject({ id: null, event: 'done' })
  })
})

function streamOf(text: string, opts: { hang?: boolean } = {}) {
  const enc = new TextEncoder()
  return new ReadableStream<Uint8Array>({
    start(c) {
      c.enqueue(enc.encode(text))
      if (!opts.hang) c.close()
    },
  })
}

describe('runSse reconnect', () => {
  it('resumes with Last-Event-ID after a dropped stream and stops at done', async () => {
    const seen: (string | null)[] = []
    const responses = [
      () => new Response(streamOf('id: 1\nevent: node_started\ndata: {"node":"plan"}\n\nid: 2\nevent: node_finished\ndata: {"node":"plan"}\n\n')),
      () => new Response(streamOf('id: 3\nevent: node_started\ndata: {"node":"retrieve"}\n\nevent: done\ndata: {"status":"completed"}\n\n')),
    ]
    let last = 0
    const states: ConnectionState[] = []
    const msgs: RawSse[] = []
    await runSse({
      url: 'http://x/events',
      headers: () => ({}),
      signal: new AbortController().signal,
      getLastEventId: () => last,
      onMessage: (m) => { msgs.push(m); if (m.id) last = Number(m.id) },
      onState: (s) => states.push(s),
      sleep: async () => {},
      fetchImpl: (async (_u: string, init: RequestInit) => {
        seen.push(new Headers(init.headers).get('Last-Event-ID'))
        return responses.shift()!()
      }),
    })
    expect(seen).toEqual([null, '2'])
    expect(msgs.map((m) => m.id)).toEqual(['1', '2', '3', null])
    expect(states.map((s) => s.phase)).toEqual(['connecting', 'open', 'reconnecting', 'open', 'closed'])
  })

  it('fails fatally on 401 without retrying', async () => {
    let calls = 0
    const states: ConnectionState[] = []
    await runSse({
      url: 'http://x', headers: () => ({}), signal: new AbortController().signal, getLastEventId: () => 0,
      onMessage: () => {}, onState: (s) => states.push(s), sleep: async () => {},
      fetchImpl: (async () => { calls++; return new Response('no', { status: 401 }) }),
    })
    expect(calls).toBe(1)
    expect(states.at(-1)).toMatchObject({ phase: 'failed', fatal: true, status: 401 })
  })

  it('gives up with a non-fatal failure after maxAttempts', async () => {
    let calls = 0
    const states: ConnectionState[] = []
    await runSse({
      url: 'http://x', headers: () => ({}), signal: new AbortController().signal, getLastEventId: () => 0,
      onMessage: () => {}, onState: (s) => states.push(s), sleep: async () => {}, maxAttempts: 3,
      fetchImpl: (async () => { calls++; throw new TypeError('network down') }),
    })
    expect(calls).toBe(4)
    expect(states.at(-1)).toMatchObject({ phase: 'failed', fatal: false })
  })

  it('backs off exponentially, capped', async () => {
    const delays: number[] = []
    await runSse({
      url: 'http://x', headers: () => ({}), signal: new AbortController().signal, getLastEventId: () => 0,
      onMessage: () => {}, onState: (s) => { if (s.phase === 'reconnecting') delays.push(s.delayMs) },
      sleep: async () => {}, maxAttempts: 5, baseDelayMs: 1000, maxDelayMs: 4000,
      fetchImpl: (async () => { throw new TypeError('x') }),
    })
    expect(delays).toEqual([1000, 2000, 4000, 4000, 4000])
  })
})
