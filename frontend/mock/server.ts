import { MockBackend } from './backend'
import { handle } from './http'

const port = Number(process.env.MOCK_PORT ?? 8788)
const backend = new MockBackend({ stepDelayMs: Number(process.env.MOCK_STEP_MS ?? 120) })

Bun.serve({ port, idleTimeout: 0, fetch: (req) => handle(req, backend, 50, { allowAnonymous: process.env.MOCK_OPEN === '1' }) })
console.log(`RepoSage mock API listening on http://127.0.0.1:${port}`)
