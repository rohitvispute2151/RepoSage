import axe, { type Result } from 'axe-core'
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { ids } from '@mock/backend'
import { backend, byTestId, clickTestId, mountApp, server, unmountAll } from '../helpers/harness'

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())
beforeEach(() => backend.reset())
afterEach(unmountAll)

// jsdom has no layout engine, so colour contrast is checked in the real browser (Playwright) instead.
const audit = async (): Promise<Result[]> => (await axe.run(document.body, { rules: { 'color-contrast': { enabled: false } } })).violations
const describeViolations = (v: Result[]) => v.map((x) => `${x.id} (${x.impact}): ${x.nodes.map((n) => n.target.join(' ')).join(' | ')}`)
const until = (fn: () => void) => vi.waitFor(fn, { timeout: 4000, interval: 20 })

describe('axe: zero violations of any impact in jsdom', () => {
  it('home', async () => {
    await mountApp('/')
    expect(describeViolations(await audit())).toEqual([])
  })

  it('trajectory with live data', async () => {
    await mountApp(`/tasks/${ids.fix}`)
    await until(() => expect(document.body.querySelector('[data-status=awaiting_approval]')).not.toBeNull())
    await until(() => expect(document.body.querySelectorAll('[data-testid="tool-table"] tbody tr').length).toBe(3))
    expect(describeViolations(await audit())).toEqual([])
  })

  it('review panel, then with the approve dialog open', async () => {
    await mountApp(`/tasks/${ids.fix}/review`)
    await until(() => expect(byTestId('approval-panel')).not.toBeNull())
    expect(describeViolations(await audit())).toEqual([])
    clickTestId('approve')
    await until(() => expect(byTestId('dialog-confirm')).not.toBeNull())
    expect(describeViolations(await audit())).toEqual([])
  })

  it.each([ids.qa, ids.qaNotFound, ids.qaUncited])('answer %s', async (id) => {
    await mountApp(`/tasks/${id}/answer`)
    await until(() => expect(document.body.querySelector('[data-testid=answer],[data-testid=not-found]')).not.toBeNull())
    expect(describeViolations(await audit())).toEqual([])
  })

  it.each([ids.queued, ids.failed, ids.budget, ids.timeout, ids.unknownStatus])('trajectory state %s', async (id) => {
    await mountApp(`/tasks/${id}`)
    await until(() => expect(byTestId('status-summary')).not.toBeNull())
    expect(describeViolations(await audit())).toEqual([])
  })

  it('error state', async () => {
    await mountApp(`/tasks/${ids.missing}`)
    await until(() => expect(byTestId('error-state')).not.toBeNull())
    expect(describeViolations(await audit())).toEqual([])
  })

  it('eval compare, empty and loaded', async () => {
    const { router } = await mountApp('/evals/compare')
    expect(describeViolations(await audit())).toEqual([])
    await router.push('/evals/compare?a=run-baseline&b=run-rerank')
    await until(() => expect(byTestId('metric-table')).not.toBeNull())
    expect(describeViolations(await audit())).toEqual([])
  })
})
