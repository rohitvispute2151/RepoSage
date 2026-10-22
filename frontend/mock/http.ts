import { DEV_KEY, evalRuns, ids, type MockBackend } from './backend'

const json = (status: number, body: unknown, headers: Record<string, string> = {}) =>
  new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json', ...headers } })

const enc = new TextEncoder()

function sse(backend: MockBackend, id: string, lastEventId: string | null, signal: AbortSignal, pollMs: number) {
  const drop = backend.dropNextStreamAfter
  backend.dropNextStreamAfter = null
  backend.streamRequests.push({ taskId: id, lastEventId })
  let last = lastEventId && /^\d+$/.test(lastEventId) ? Number(lastEventId) : 0
  let sent = 0
  return new ReadableStream<Uint8Array>({
    async start(controller) {
      const close = () => { try { controller.close() } catch { /* already closed */ } }
      signal.addEventListener('abort', close, { once: true })
      while (!signal.aborted) {
        for (const e of backend.eventsAfter(id, last)) {
          last = e.seq
          controller.enqueue(enc.encode(`id: ${e.seq}\nevent: ${e.type}\ndata: ${JSON.stringify(e.payload)}\n\n`))
          sent++
          if (drop !== null && sent >= drop) return close()
        }
        if (backend.isTerminal(id)) {
          controller.enqueue(enc.encode(`event: done\ndata: ${JSON.stringify({ status: backend.status(id) })}\n\n`))
          return close()
        }
        await new Promise((r) => setTimeout(r, pollMs))
      }
    },
  })
}

/** Web-standard request handler: used by MSW (tests) and Bun.serve (Playwright mock server). */
export async function handle(req: Request, backend: MockBackend, pollMs = 25, opts: { allowAnonymous?: boolean } = {}): Promise<Response> {
  const url = new URL(req.url)
  const path = url.pathname
  const cors = { 'access-control-allow-origin': '*', 'access-control-allow-headers': '*' }

  if (req.method === 'OPTIONS') return new Response(null, { status: 204, headers: cors })

  // test control plane
  if (path === '/__mock/reset') { backend.reset(); return json(200, { ok: true }) }
  if (path === '/__mock/drop-next-stream') { backend.dropNextStreamAfter = Number(url.searchParams.get('after') ?? 3); return json(200, { ok: true }) }
  if (path.startsWith('/__mock/rotate-patch/')) return json(backend.rotatePatch(path.split('/').pop()!) ? 200 : 404, { ok: true })
  if (path.startsWith('/__mock/events/')) return json(200, backend.eventsAfter(path.split('/').pop()!, 0))
  if (path === '/__mock/approvals') return json(200, backend.approvals)
  if (path === '/__mock/streams') return json(200, backend.streamRequests)

  if (path === '/healthz') return json(200, { status: 'ok' })
  if (path === '/readyz') return json(200, { status: 'ready' })
  if (!path.startsWith('/v1/')) return json(404, { detail: 'Not Found' })

  const key = req.headers.get('x-api-key')
  if (!key && !opts.allowAnonymous) return json(401, { detail: 'Missing required X-API-Key header' })
  if (key && key !== DEV_KEY) return json(403, { detail: 'Invalid X-API-Key provided' })

  if (path === '/v1/repos' && req.method === 'POST') {
    const out = backend.registerRepo((await req.json().catch(() => ({}))) as Record<string, string>)
    return json(out.status, out.body)
  }
  if (path === '/v1/repos' && req.method === 'GET') {
    const out = backend.listRepos(new URL(req.url).searchParams)
    return json(out.status, out.body)
  }
  const snap = /^\/v1\/repos\/([^/]+)$/.exec(path)
  if (snap && req.method === 'GET') {
    const s = backend.snapshotJson(snap[1]!)
    return s ? json(200, s) : json(404, { detail: `Snapshot ${snap[1]} not found` })
  }
  if (path === '/v1/tasks' && req.method === 'POST') {
    const out = backend.createTask((await req.json().catch(() => ({}))) as Record<string, never>)
    return json(out.status, out.body)
  }
  const cancel = /^\/v1\/tasks\/([^/]+)\/cancel$/.exec(path)
  if (cancel && req.method === 'POST') {
    const out = backend.cancel(cancel[1]!)
    return json(out.status, out.body)
  }

  const run = /^\/v1\/evals\/runs\/([^/]+)$/.exec(path)
  if (run) {
    const r = evalRuns[decodeURIComponent(run[1]!)]
    return r ? json(200, r) : json(404, { detail: 'Eval run not found' })
  }

  const m = /^\/v1\/tasks\/([^/]+)(\/events|\/approval)?$/.exec(path)
  if (!m) return json(404, { detail: 'Not Found' })
  const id = m[1]!
  if (id === ids.missing || !backend.tasks.has(id)) return json(404, { detail: `Task ${id} not found` })
  backend.ensureStarted(id)

  if (m[2] === '/events' && req.method === 'GET') {
    return new Response(sse(backend, id, req.headers.get('last-event-id'), req.signal, pollMs), {
      headers: { 'content-type': 'text/event-stream', 'cache-control': 'no-cache', ...cors },
    })
  }
  if (m[2] === '/approval' && req.method === 'POST') {
    const body = (await req.json().catch(() => ({}))) as Record<string, unknown>
    const out = backend.decide(id, body)
    return json(out.status === 200 ? 200 : out.status, out.body)
  }
  if (!m[2] && req.method === 'GET') {
    if (id === ids.queued && url.searchParams.get('boom')) return json(500, { detail: 'boom' })
    return json(200, backend.taskJson(id))
  }
  return json(405, { detail: 'Method Not Allowed' })
}
