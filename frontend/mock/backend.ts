/**
 * In-memory stand-in for the RepoSage API, shared by the MSW tests and the Playwright mock server.
 * It enforces the same rules as src/reposage/api/routes_tasks.py (auth, 409 on wrong status or stale sha,
 * 422 on edit without a diff) so UI behaviour against it reflects the real contract.
 *
 * It also emits `tool_call` and `budget` events, which LLD §3 documents but the real worker does not emit yet.
 */
import { createHash } from 'node:crypto'

export const DEV_KEY = 'reposage-dev-key'
export const ids = {
  fix: '11111111-1111-4111-8111-111111111111',
  qa: '22222222-2222-4222-8222-222222222222',
  qaNotFound: '23232323-2323-4323-8323-232323232323',
  qaUncited: '24242424-2424-4424-8424-242424242424',
  queued: '33333333-3333-4333-8333-333333333333',
  failed: '44444444-4444-4444-8444-444444444444',
  budget: '55555555-5555-4555-8555-555555555555',
  cancelled: '66666666-6666-4666-8666-666666666666',
  timeout: '77777777-7777-4777-8777-777777777777',
  broken: '88888888-8888-4888-8888-888888888888',
  unknownStatus: '99999999-9999-4999-8999-999999999999',
  missing: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
} as const

export const sha256 = (s: string) => createHash('sha256').update(s).digest('hex')

export const PATCH_V1 = `diff --git a/src/pkg/http.py b/src/pkg/http.py
--- a/src/pkg/http.py
+++ b/src/pkg/http.py
@@ -41,5 +41,5 @@ def compute_backoff(attempt: int, base: float = 0.5) -> float:
     # <img src=x onerror="window.__pwned = 1">  (repo comment, must stay inert)
-    return base * 2 * attempt
+    return base * 2 ** attempt
 
 
 def should_retry(status: int) -> bool:
`

export const RATIONALE = `Backoff used multiplication instead of exponentiation.
<script>window.__pwned = 1</script>`

export const EVIDENCE = { all_target_pass: true, regressions: 0, policy_ok: true, failure_digest: '' }

export interface MockEvent { seq: number; type: string; payload: Record<string, unknown> }

interface MockTask {
  id: string
  mode: 'qa' | 'fix'
  status: string
  outcome: string | null
  result: Record<string, unknown> | null
  events: MockEvent[]
  patch: { id: string; diff: string; sha256: string } | null
  created_at: string
  started: boolean
  broken?: boolean
}

export interface ApprovalRecord { taskId: string; decision: string; patch_sha256: string; edited_diff?: string | null; comment?: string | null; status: number }

const BUDGETS = { max_steps: 30, max_tokens: 250000, max_usd: 1, max_seconds: 900 }
const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms))

export class MockBackend {
  tasks = new Map<string, MockTask>()
  approvals: ApprovalRecord[] = []
  streamRequests: { taskId: string; lastEventId: string | null }[] = []
  /** Close the next event stream after this many events without sending `done` (simulated network drop). */
  dropNextStreamAfter: number | null = null
  stepDelayMs: number
  /** Pause before the worker "resumes" after a decision, so a UI can be observed in its post-submit state. */
  resumeDelayMs = 0

  constructor(opts: { stepDelayMs?: number } = {}) {
    this.stepDelayMs = opts.stepDelayMs ?? 0
    this.reset()
  }

  reset() {
    this.tasks.clear()
    this.snapshots.clear()
    this.names.clear()
    this.approvals = []
    this.streamRequests = []
    this.dropNextStreamAfter = null
    this.resumeDelayMs = 0
    const now = new Date().toISOString()
    const mk = (id: string, mode: 'qa' | 'fix', status: string, extra: Partial<MockTask> = {}) =>
      this.tasks.set(id, { id, mode, status, outcome: null, result: null, events: [], patch: null, created_at: now, started: true, ...extra })

    mk(ids.fix, 'fix', 'queued', { started: false })
    mk(ids.queued, 'fix', 'queued')
    mk(ids.failed, 'fix', 'failed', { outcome: 'failed' })
    mk(ids.budget, 'qa', 'budget_exceeded', { outcome: 'budget_exceeded', result: { outcome: 'budget_exceeded', budget_report: { steps: 30, tokens: 120000, usd: 0.42, seconds: 310, limits: BUDGETS }, notes: ['Task halted early due to budget breach: budget_exceeded:steps'] } })
    mk(ids.cancelled, 'fix', 'cancelled', { outcome: 'cancelled_by_user' })
    mk(ids.timeout, 'fix', 'approval_timeout', { outcome: 'approval_timeout', result: { outcome: 'approval_timeout', patch_diff: PATCH_V1, test_summary: EVIDENCE, budget_report: {}, notes: [] } })
    mk(ids.broken, 'qa', 'completed', { broken: true })
    mk(ids.unknownStatus, 'fix', 'frozen')
    const cite = { path: 'src/pkg/http.py', start_line: 38, end_line: 44, symbol: 'pkg.http.compute_backoff' }
    mk(ids.qa, 'qa', 'completed', {
      outcome: 'answered',
      result: {
        outcome: 'answered',
        answer: 'Retry backoff is computed in `compute_backoff`, which doubles the base delay per attempt.\n<img src=x onerror="window.__pwned = 1">',
        citations: [cite, { path: 'src/pkg/<b>client</b>.py', start_line: 10, end_line: 10, symbol: 'Client.send' }],
        budget_report: { steps: 6, tokens: 9100, usd: 0.03, seconds: 14, limits: BUDGETS },
        notes: ['Filtered invalid citation docs/old.py:3: file_missing'],
      },
    })
    mk(ids.qaNotFound, 'qa', 'completed', { outcome: 'answered', result: { outcome: 'answered', answer: 'Unable to locate answer.', found: false, citations: [], budget_report: {}, notes: [] } })
    mk(ids.qaUncited, 'qa', 'completed', { outcome: 'answered', result: { outcome: 'answered', answer: 'It is probably in the http module.', citations: [], budget_report: {}, notes: [] } })
  }

  private push(t: MockTask, type: string, payload: Record<string, unknown>) {
    t.events.push({ seq: t.events.length + 1, type, payload })
  }

  /** Scripted fix run, started lazily on first access so each test sees it from the beginning. */
  ensureStarted(id: string) {
    const t = this.tasks.get(id)
    if (!t || t.started) return
    t.started = true
    void (t.mode === 'qa' ? this.playQa(t) : this.playFix(t))
  }

  private async playQa(t: MockTask) {
    const step = async () => { if (this.stepDelayMs) await sleep(this.stepDelayMs); else await Promise.resolve() }
    t.status = 'running'
    const script: [string, Record<string, unknown>][] = [
      ['node_started', { node: 'plan' }], ['node_finished', { node: 'plan' }],
      ['node_started', { node: 'retrieve' }], ['node_finished', { node: 'retrieve' }],
      ['node_started', { node: 'explore' }],
      ['tool_call', { tool: 'search_code', status: 'ok', duration_ms: 70, node: 'explore' }],
      ['tool_call', { tool: 'read_file', status: 'ok', duration_ms: 5, node: 'explore' }],
      ['budget', { steps: 3, tokens: 6400, usd: 0.02, seconds: 9, limits: BUDGETS }],
      ['node_finished', { node: 'explore' }],
      ['node_started', { node: 'report' }],
    ]
    for (const [type, payload] of script) { await step(); if (t.status === 'cancelled') return; this.push(t, type, payload) }
    await step()
    if (t.status === 'cancelled') return
    t.outcome = 'answered'
    t.result = { outcome: 'answered', answer: 'Retry backoff is computed in compute_backoff.', citations: [{ path: 'src/pkg/http.py', start_line: 38, end_line: 44, symbol: 'pkg.http.compute_backoff' }], budget_report: { steps: 5, tokens: 9100, usd: 0.03, seconds: 14, limits: BUDGETS }, notes: [] }
    t.status = 'completed'
    this.push(t, 'completed', { status: 'completed', outcome: 'answered' })
  }

  private async playFix(t: MockTask) {
    const step = async () => { if (this.stepDelayMs) await sleep(this.stepDelayMs); else await Promise.resolve() }
    t.status = 'running'
    const script: [string, Record<string, unknown>][] = [
      ['node_started', { node: 'plan' }],
      ['node_finished', { node: 'plan' }],
      ['node_started', { node: 'retrieve' }],
      ['node_finished', { node: 'retrieve' }],
      ['node_started', { node: 'explore' }],
      ['tool_call', { tool: 'search_code', status: 'ok', duration_ms: 84, node: 'explore' }],
      ['tool_call', { tool: 'read_file', status: 'ok', duration_ms: 6, node: 'explore' }],
      ['tool_call', { tool: 'read_file', status: 'denied', denial_reason: 'path_escape', duration_ms: 1, node: 'explore' }],
      ['budget', { steps: 4, tokens: 18200, usd: 0.07, seconds: 21, limits: BUDGETS }],
      ['node_finished', { node: 'explore' }],
      ['node_started', { node: 'patch' }],
      ['node_finished', { node: 'patch', validation: true }],
      ['node_started', { node: 'verify' }],
      ['node_finished', { node: 'verify', passed: true }],
    ]
    for (const [type, payload] of script) { await step(); if (t.status === 'cancelled') return; this.push(t, type, payload) }
    await step()
    if (t.status === 'cancelled') return
    this.requestApproval(t, PATCH_V1, RATIONALE)
  }

  private requestApproval(t: MockTask, diff: string, rationale: string) {
    t.patch = { id: crypto.randomUUID(), diff, sha256: sha256(diff) }
    t.status = 'awaiting_approval'
    this.push(t, 'approval_requested', { patch_id: t.patch.id, diff, sha256: t.patch.sha256, test_evidence: EVIDENCE, rationale })
  }

  /** Simulates the agent producing a different patch while a reviewer still holds the old hash. */
  rotatePatch(id: string) {
    const t = this.tasks.get(id)
    if (!t) return false
    this.requestApproval(t, PATCH_V1.replace('base * 2 ** attempt', 'base * (2 ** attempt)'), 'Parenthesised for clarity.')
    return true
  }

  snapshots = new Map<string, { id: string; repo_id: string; commit_sha: string; status: string; mirror_path: string; repo_map: Record<string, unknown> | null; error: string | null; created_at: string; polls: number; fail: boolean }>()

  registerRepo(body: { name?: string; source_uri?: string; commit_sha?: string }) {
    if (!body.name || !body.source_uri || !body.commit_sha || body.commit_sha.length < 7) return { status: 422, body: { detail: [{ loc: ['body'], msg: 'Field required', type: 'missing' }] } }
    if (body.source_uri.includes('missing')) return { status: 400, body: { detail: `Failed to clone repository from ${body.source_uri}: repository not found` } }
    const id = crypto.randomUUID()
    this.names.set(id, { name: body.name, source: body.source_uri })
    this.snapshots.set(id, { id, repo_id: crypto.randomUUID(), commit_sha: body.commit_sha, status: 'queued', mirror_path: `/data/${id}`, repo_map: null, error: null, created_at: new Date().toISOString(), polls: 0, fail: body.source_uri.includes('broken') })
    return { status: 202, body: this.snapshotJson(id) }
  }

  names = new Map<string, { name: string; source: string }>()

  /** Newest first, like the real endpoint. Listing does not advance ingestion; only polling one snapshot does. */
  listRepos(query: URLSearchParams) {
    const status = query.get('status')
    const limit = Number(query.get('limit') ?? 50)
    const offset = Number(query.get('offset') ?? 0)
    const all = [...this.snapshots.values()].filter((s) => !status || s.status === status).sort((a, b) => b.created_at.localeCompare(a.created_at))
    const items = all.slice(offset, offset + limit).map((s) => ({
      id: s.id, repo_id: s.repo_id, name: this.names.get(s.id)?.name ?? 'repo', source_uri: this.names.get(s.id)?.source ?? '', commit_sha: s.commit_sha,
      status: s.status, error: s.error, chunk_count: s.status === 'ready' ? 42 : 0, created_at: s.created_at,
    }))
    return { status: 200, body: { items, total: all.length, limit, offset } }
  }

  /** Each poll advances queued -> ingesting -> ready (or failed) so the UI can show progress. */
  snapshotJson(id: string) {
    const s = this.snapshots.get(id)
    if (!s) return null
    s.polls++
    if (s.polls > 2) { s.status = s.fail ? 'failed' : 'ready'; s.error = s.fail ? 'ingestion crashed: syntax error in setup.py' : null; s.repo_map = s.fail ? null : { 'pkg.http': ['compute_backoff', 'should_retry'], 'pkg.client': ['Client.send'] } }
    else if (s.polls > 1) s.status = 'ingesting'
    return { id: s.id, repo_id: s.repo_id, commit_sha: s.commit_sha, status: s.status, mirror_path: s.mirror_path, repo_map: s.repo_map, error: s.error, created_at: s.created_at }
  }

  createTask(body: { snapshot_id?: string; mode?: string; qa?: { question?: string }; fix?: { failing_tests?: string[] } }) {
    if (!body.snapshot_id || !this.snapshots.has(body.snapshot_id)) return { status: 404, body: { detail: `Snapshot ${body.snapshot_id} not found` } }
    if (body.mode === 'qa' && !body.qa) return { status: 422, body: { detail: "qa field is required when mode is 'qa'" } }
    if (body.mode === 'fix' && !body.fix) return { status: 422, body: { detail: "fix field is required when mode is 'fix'" } }
    const id = crypto.randomUUID()
    const mode = body.mode === 'fix' ? 'fix' : 'qa'
    this.tasks.set(id, { id, mode, status: 'queued', outcome: null, result: null, events: [], patch: null, created_at: new Date().toISOString(), started: false })
    return { status: 202, body: this.taskJson(id) }
  }

  cancel(id: string) {
    const t = this.tasks.get(id)
    if (!t) return { status: 404, body: { detail: 'Task not found' } }
    if (!['queued', 'running', 'awaiting_approval'].includes(t.status)) return { status: 409, body: { detail: `Cannot transition task ${id} from '${t.status}' to 'cancelled'` } }
    t.status = 'cancelled'
    t.outcome = 'cancelled_by_user'
    return { status: 200, body: { status: 'cancelled' } }
  }

  taskJson(id: string) {
    const t = this.tasks.get(id)
    if (!t) return null
    return { id: t.id, snapshot_id: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb', mode: t.mode, status: t.status, outcome: t.outcome, budgets: BUDGETS, result: t.broken ? { answer: 42 } : t.result, created_at: t.created_at, updated_at: new Date().toISOString() }
  }

  isTerminal(id: string) {
    const s = this.tasks.get(id)?.status
    return !!s && ['completed', 'failed', 'budget_exceeded', 'cancelled', 'approval_timeout'].includes(s)
  }

  eventsAfter(id: string, seq: number) { return (this.tasks.get(id)?.events ?? []).filter((e) => e.seq > seq) }
  status(id: string) { return this.tasks.get(id)?.status ?? null }

  decide(id: string, body: { decision?: string; patch_sha256?: string; edited_diff?: string | null; comment?: string | null }): { status: number; body: unknown } {
    const t = this.tasks.get(id)
    const rec = (status: number) => this.approvals.push({ taskId: id, decision: String(body.decision), patch_sha256: String(body.patch_sha256), edited_diff: body.edited_diff, comment: body.comment, status })
    if (!t) return { status: 404, body: { detail: 'Task not found' } }
    if (!['approve', 'reject', 'edit'].includes(String(body.decision)) || typeof body.patch_sha256 !== 'string') {
      rec(422)
      return { status: 422, body: { detail: [{ loc: ['body'], msg: 'Field required', type: 'missing' }] } }
    }
    if (t.status !== 'awaiting_approval') {
      rec(409)
      return { status: 409, body: { detail: `Task is in status '${t.status}', not 'awaiting_approval'` } }
    }
    if (!t.patch || t.patch.sha256 !== body.patch_sha256) {
      rec(409)
      return { status: 409, body: { detail: 'Patch changed or hash mismatch; refetch before deciding' } }
    }
    if (body.decision === 'edit' && !body.edited_diff) {
      rec(422)
      return { status: 422, body: { detail: 'edited_diff is required when decision is \'edit\'' } }
    }
    rec(200)
    void this.resume(t, body)
    return { status: 200, body: { status: 'accepted' } }
  }

  private async resume(t: MockTask, body: { decision?: string; edited_diff?: string | null; comment?: string | null }) {
    await sleep(this.resumeDelayMs)
    const diff = t.patch!.diff
    if (body.decision === 'edit') {
      t.status = 'running'
      this.push(t, 'node_started', { node: 'verify' })
      this.push(t, 'node_finished', { node: 'verify', passed: true })
      this.requestApproval(t, body.edited_diff!, 'Human edited patch')
      return
    }
    const applied = body.decision === 'approve'
    t.status = 'running'
    this.push(t, applied ? 'patch_applied' : 'patch_rejected', applied ? { applied: true, error: null } : { comment: body.comment ?? null })
    this.push(t, 'node_started', { node: 'report' })
    const outcome = applied ? 'patch_applied' : 'patch_rejected'
    t.outcome = outcome
    t.result = { outcome, patch_diff: diff, test_summary: EVIDENCE, rationale: RATIONALE, applied, budget_report: { steps: 9, tokens: 31200, usd: 0.11, seconds: 48, limits: BUDGETS }, notes: [] }
    t.status = 'completed'
    this.push(t, 'completed', { status: 'completed', outcome })
  }
}

// ---- Eval fixtures -------------------------------------------------------------------------

function rng(seed: number) {
  let s = seed
  return () => { s = (s * 1664525 + 1013904223) % 4294967296; return s / 4294967296 }
}

export function makeEvalRun(id: string, label: string, opts: { seed: number; recallBase: number; mrrBase: number; noise: number; repeats: number; cases?: number; dropCases?: number }) {
  const rand = rng(opts.seed)
  const results = []
  const nCases = opts.cases ?? 12
  for (let r = 0; r < opts.repeats; r++) {
    const runShift = (rand() - 0.5) * 2 * opts.noise
    for (let c = 0; c < nCases - (opts.dropCases ?? 0); c++) {
      const caseId = `case-${String(c + 1).padStart(2, '0')}`
      const jitter = (rand() - 0.5) * 0.05
      results.push({ case_id: caseId, repeat_idx: r, metrics: { recall_at_5: Math.min(1, Math.max(0, opts.recallBase + runShift + jitter)), mrr: Math.min(1, Math.max(0, opts.mrrBase + runShift / 2 + jitter)), top_symbols: ['pkg.a'] } })
    }
  }
  return { run: { id, label, config_fingerprint: `fp-${label}`, started_at: '2026-10-01T10:00:00Z', finished_at: '2026-10-01T10:20:00Z' }, results }
}

export const evalRuns: Record<string, ReturnType<typeof makeEvalRun>> = {
  'run-baseline': makeEvalRun('run-baseline', 'baseline', { seed: 7, recallBase: 0.6, mrrBase: 0.5, noise: 0.01, repeats: 3 }),
  'run-rerank': makeEvalRun('run-rerank', 'rerank_on', { seed: 11, recallBase: 0.75, mrrBase: 0.505, noise: 0.01, repeats: 3, dropCases: 1 }),
}

export const HOSTILE = '<img src=x onerror="window.__pwned=1"><script>window.__pwned=1</script><svg onload="window.__pwned=1">'
evalRuns['run-hostile'] = makeEvalRun('run-hostile', `lbl${HOSTILE}`, { seed: 3, recallBase: 0.5, mrrBase: 0.5, noise: 0.01, repeats: 2, cases: 2 })
evalRuns['run-hostile']!.results = evalRuns['run-hostile']!.results.map((r) => ({ ...r, case_id: `${r.case_id}${HOSTILE}` }))
