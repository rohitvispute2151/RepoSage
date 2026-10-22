import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { ids } from '@mock/backend'
import { API, backend, byTestId, mountApp, server, text, unmountAll } from '../helpers/harness'

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())
beforeEach(() => backend.reset())
afterEach(() => {
  unmountAll()
  server.resetHandlers()
})

const until = (fn: () => void, timeout = 4000) => vi.waitFor(fn, { timeout, interval: 20 })
const badge = () => document.body.querySelector('header [data-status], main [data-status]')?.getAttribute('data-status')

describe('every task status is a real state', () => {
  const cases: [string, string, string][] = [
    [ids.queued, 'queued', 'Waiting for a worker'],
    [ids.failed, 'failed', 'The task failed'],
    [ids.budget, 'budget_exceeded', 'limit was hit'],
    [ids.cancelled, 'cancelled', 'was cancelled'],
    [ids.timeout, 'approval_timeout', 'discarded and nothing was applied'],
    [ids.qa, 'completed', 'The task finished'],
    [ids.unknownStatus, 'unknown', 'out of sync'],
  ]
  it.each(cases)('%s renders as %s', async (id, status, summary) => {
    await mountApp(`/tasks/${id}`)
    await until(() => expect(badge()).toBe(status))
    expect(byTestId('status-summary')?.textContent).toContain(summary)
  })

  it('shows the raw value when the server sends a status the console does not know', async () => {
    await mountApp(`/tasks/${ids.unknownStatus}`)
    await until(() => expect(text()).toContain('Unknown status (frozen)'))
  })

  it('running and awaiting_approval are covered by the scripted fix flow', async () => {
    await mountApp(`/tasks/${ids.fix}`)
    await until(() => expect(badge()).toBe('awaiting_approval'))
  })
})

describe('patch review for terminal states', () => {
  it('approval_timeout shows the discarded patch as not applied and offers no decision buttons', async () => {
    await mountApp(`/tasks/${ids.timeout}/review`)
    await until(() => expect(byTestId('final-patch')).not.toBeNull())
    expect(text()).toContain('approval window closed')
    expect(text()).toContain('not applied')
    expect(byTestId('approve')).toBeNull()
  })

  it('a task that finished without a patch says so', async () => {
    await mountApp(`/tasks/${ids.failed}/review`)
    await until(() => expect(text()).toContain('finished without a patch'))
  })

  it('a queued task has an empty state, not a blank page', async () => {
    await mountApp(`/tasks/${ids.queued}/review`)
    await until(() => expect(text()).toContain('No patch to review yet'))
  })
})

describe('trajectory empty and degraded states', () => {
  it('queued task: no events, no tool calls, budget not reported', async () => {
    await mountApp(`/tasks/${ids.queued}`)
    await until(() => expect(text()).toContain('The task is queued. Events start once a worker picks it up.'))
    expect(text()).toContain('No tool calls reported')
    expect(byTestId('budget-tokens')?.textContent).toContain('not reported')
  })

  it('budget_exceeded task shows the final usage against limits', async () => {
    await mountApp(`/tasks/${ids.budget}`)
    await until(() => expect(byTestId('budget-steps')?.textContent).toMatch(/30\s*\/\s*30/))
    expect(byTestId('budget-steps')?.textContent).toContain('Over 85%')
  })

  it('marks malformed and unknown events instead of dropping them', async () => {
    const bad = http.get(`${API}/v1/tasks/:id/events`, () =>
      new HttpResponse(
        'id: 1\nevent: node_started\ndata: {"node": 5}\n\nid: 2\nevent: mystery\ndata: {}\n\nid: 3\nevent: node_started\ndata: {"node":"plan"}\n\n',
        { headers: { 'content-type': 'text/event-stream' } },
      ),
    )
    server.use(bad)
    await mountApp(`/tasks/${ids.queued}`)
    await until(() => expect(text()).toContain('1 malformed'))
    expect(text()).toContain('1 unrecognised')
    expect(byTestId('event-log')?.textContent).toContain('Started plan')
  })
})

describe('infra and auth errors', () => {
  it('404 task', async () => {
    await mountApp(`/tasks/${ids.missing}`)
    await until(() => expect(byTestId('error-state')?.textContent).toContain('Not found'))
  })

  it('missing API key → 401 explained, no retry button', async () => {
    await mountApp(`/tasks/${ids.qa}`, { apiKey: '' })
    await until(() => expect(byTestId('error-state')?.textContent).toContain('API key was rejected'))
    expect(byTestId('error-state')?.textContent).not.toContain('Retry')
  })

  it('wrong API key → 403', async () => {
    await mountApp(`/tasks/${ids.qa}`, { apiKey: 'nope' })
    await until(() => expect(byTestId('error-state')?.textContent).toContain('API key was rejected'))
  })

  it('500 is described as infrastructure trouble and can be retried', async () => {
    let calls = 0
    server.use(
      http.get(`${API}/v1/tasks/:id`, () => {
        calls++
        return calls === 1 ? HttpResponse.json({ detail: 'db down' }, { status: 500 }) : HttpResponse.json(backend.taskJson(ids.qa))
      }),
    )
    await mountApp(`/tasks/${ids.qa}`)
    await until(() => expect(byTestId('error-state')?.textContent ?? '').toContain('infrastructure error'))
    ;[...document.body.querySelectorAll('button')].find((b) => b.textContent === 'Retry')!.click()
    await until(() => expect(badge()).toBe('completed'))
  })

  it('network failure', async () => {
    server.use(http.get(`${API}/v1/tasks/:id`, () => HttpResponse.error()))
    await mountApp(`/tasks/${ids.qa}`)
    await until(() => expect(byTestId('error-state')?.textContent ?? '').toContain('Cannot reach the RepoSage API'))
  })

  it('unreadable result payload is reported, not rendered as an answer', async () => {
    await mountApp(`/tasks/${ids.broken}/answer`)
    await until(() => expect(document.body.querySelector('[role=alert]')?.textContent ?? '').toContain('could not be read'))
  })
})

describe('QA answers', () => {
  it('renders the answer and citations that carry path and line range', async () => {
    await mountApp(`/tasks/${ids.qa}/answer`)
    await until(() => expect(byTestId('answer')).not.toBeNull())
    expect(byTestId('answer-text')?.textContent).toContain('compute_backoff')
    const cites = [...document.body.querySelectorAll('[data-testid="citations"] li')]
    expect(cites).toHaveLength(2)
    expect(cites[0]?.textContent).toContain('src/pkg/http.py:38-44')
    expect(cites[0]?.textContent).toContain('pkg.http.compute_backoff')
    expect(text()).toContain('Filtered invalid citation docs/old.py:3')
  })

  it('found=false is a clear not-found state, with no citations list', async () => {
    await mountApp(`/tasks/${ids.qaNotFound}/answer`)
    await until(() => expect(byTestId('not-found')).not.toBeNull())
    expect(text()).toContain('could not find an answer')
    expect(byTestId('answer')).toBeNull()
    expect(text()).toContain('No verified citations')
  })

  it('an answer with no surviving citation is flagged as unverified', async () => {
    await mountApp(`/tasks/${ids.qaUncited}/answer`)
    await until(() => expect(byTestId('uncited')).not.toBeNull())
  })

  it('budget_exceeded QA with no answer is a partial report, not a blank', async () => {
    await mountApp(`/tasks/${ids.budget}/answer`)
    await until(() => expect(text()).toContain('budget ran out'))
  })
})

describe('eval compare', () => {
  it('shows paired deltas and run-to-run spread, with verdicts', async () => {
    await mountApp('/evals/compare?a=run-baseline&b=run-rerank')
    await until(() => expect(byTestId('metric-table')).not.toBeNull())
    const row = (m: string) => document.body.querySelector(`[data-metric="${m}"]`)!
    expect(row('recall_at_5').getAttribute('data-verdict')).toBe('improved')
    expect(row('mrr').getAttribute('data-verdict')).toBe('within-noise')
    expect(row('recall_at_5').textContent).toMatch(/±/)
    expect(byTestId('unpaired')?.textContent).toContain('1 only in A')
    expect(document.body.querySelectorAll('details').length).toBe(2)
  })

  it('unknown run id surfaces a not-found error for that side only', async () => {
    await mountApp('/evals/compare?a=run-baseline&b=nope')
    await until(() => expect(byTestId('error-state')?.textContent).toContain('Not found'))
    expect(byTestId('run-a-meta')).not.toBeNull()
    expect(text()).toContain('Load two runs to compare')
  })

  it('warns when both runs share a config fingerprint', async () => {
    await mountApp('/evals/compare?a=run-baseline&b=run-baseline')
    await until(() => expect(text()).toContain('same config fingerprint'))
  })
})
