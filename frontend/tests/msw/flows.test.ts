import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { ids } from '@mock/backend'
import { API, backend, byTestId, clickTestId, mountApp, server, text, unmountAll } from '../helpers/harness'

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())
beforeEach(() => { backend.reset(); localStorage.clear() })
afterEach(() => { unmountAll(); server.resetHandlers() })

const until = (fn: () => void, timeout = 5000) => vi.waitFor(fn, { timeout, interval: 20 })
const set = (sel: string, value: string) => {
  const el = document.body.querySelector<HTMLInputElement | HTMLTextAreaElement>(sel)!
  el.value = value
  el.dispatchEvent(new Event('input'))
}
const submit = (form = 'form') => document.body.querySelector<HTMLFormElement>(form)!.dispatchEvent(new Event('submit', { cancelable: true }))

describe('home', () => {
  it('shows API liveness and readiness', async () => {
    await mountApp('/')
    await until(() => expect(byTestId('api-status')?.textContent).toContain('Database ready'))
  })
  it('says so when the API is unreachable', async () => {
    server.use(http.get(`${API}/healthz`, () => HttpResponse.error()), http.get(`${API}/readyz`, () => HttpResponse.error()))
    await mountApp('/')
    await until(() => expect(byTestId('api-status')?.textContent).toContain('Unreachable'))
  })
  it('flags a database that is not ready', async () => {
    server.use(http.get(`${API}/readyz`, () => HttpResponse.json({ status: 'unhealthy', error: 'x' })))
    await mountApp('/')
    await until(() => expect(byTestId('api-status')?.textContent).toContain('Database not ready'))
  })
  it('lists tasks opened in this browser', async () => {
    const { router } = await mountApp(`/tasks/${ids.qa}`)
    await until(() => expect(byTestId('status-summary')).not.toBeNull())
    await router.push('/')
    await until(() => expect(byTestId('recent-tasks')?.textContent).toContain(ids.qa))
  })
})

describe('repositories', () => {
  it('validates before sending anything', async () => {
    await mountApp('/repos')
    submit()
    await until(() => expect(text()).toContain('Enter a commit SHA'))
    expect(backend.snapshots.size).toBe(0)
  })

  it('registers a repo and follows indexing from queued to ready, then offers a task', async () => {
    const { router } = await mountApp('/repos')
    set('#repo-name', 'svc'); set('#repo-source_uri', 'https://example.com/svc.git'); set('#repo-commit_sha', '3c47104')
    submit()
    await until(() => expect(document.body.querySelector('[data-testid^=snapshot-]')).not.toBeNull())
    await until(() => expect(document.body.querySelector('[data-testid^=snapshot-]')?.getAttribute('data-status')).toBe('ready'), 8000)
    expect(text()).toContain('Repo map (2 modules)')
    ;[...document.body.querySelectorAll('button')].find((b) => b.textContent?.includes('Start a task'))!.click()
    await until(() => expect(router.currentRoute.value.name).toBe('new-task'))
    expect(router.currentRoute.value.query.snapshot).toBe([...backend.snapshots.keys()][0])
  })

  it('lists repositories registered on the server, even ones this browser never saw', async () => {
    backend.registerRepo({ name: 'billing-svc', source_uri: 'https://example.com/billing.git', commit_sha: 'abcdef1' })
    backend.registerRepo({ name: 'auth-svc', source_uri: '/srv/auth', commit_sha: '1234567' })
    localStorage.clear()
    await mountApp('/repos')
    await until(() => expect(document.body.querySelectorAll('[data-testid^=snapshot-]:not([data-testid=snapshot-source])').length).toBe(2))
    expect(byTestId('repo-total')?.textContent).toContain('2')
    expect(text()).toContain('billing-svc')
    expect(text()).toContain('https://example.com/billing.git')
    expect(text()).toContain('auth-svc')
  })

  it('shows an empty state when the server has nothing registered', async () => {
    localStorage.clear()
    await mountApp('/repos')
    await until(() => expect(text()).toContain('Nothing is registered on this server'))
  })

  it('refreshes the list after a registration instead of relying on browser history', async () => {
    localStorage.clear()
    await mountApp('/repos')
    await until(() => expect(text()).toContain('Nothing is registered'))
    set('#repo-name', 'fresh'); set('#repo-source_uri', 'https://example.com/fresh.git'); set('#repo-commit_sha', '3c47104')
    submit()
    await until(() => expect(byTestId('repo-total')?.textContent).toContain('1'))
    expect(text()).toContain('fresh')
  })

  it('shows an ingestion failure', async () => {
    await mountApp('/repos')
    set('#repo-name', 'svc'); set('#repo-source_uri', 'https://example.com/broken.git'); set('#repo-commit_sha', '3c47104')
    submit()
    await until(() => expect(document.body.querySelector('[data-testid^=snapshot-]')?.getAttribute('data-status')).toBe('failed'), 8000)
    expect(text()).toContain('syntax error in setup.py')
  })

  it('surfaces a clone failure from the API (400)', async () => {
    await mountApp('/repos')
    set('#repo-name', 'svc'); set('#repo-source_uri', 'https://example.com/missing.git'); set('#repo-commit_sha', '3c47104')
    submit()
    await until(() => expect(byTestId('error-state')?.textContent).toContain('repository not found'))
  })
})

describe('new task and cancel', () => {
  const seedSnapshot = async () => {
    const r = backend.registerRepo({ name: 'svc', source_uri: 'x', commit_sha: '3c47104' })
    return (r.body as { id: string }).id
  }

  it('creates a QA task and lands on its live trajectory, which completes', async () => {
    const snap = await seedSnapshot()
    const { router } = await mountApp(`/tasks/new?snapshot=${snap}`)
    set('#t-q', 'Where is retry backoff computed?')
    submit()
    await until(() => expect(router.currentRoute.value.name).toBe('trajectory'))
    await until(() => expect(document.body.querySelector('[data-status=completed]')).not.toBeNull())
    expect(byTestId('outcome')?.textContent).toBe('answered')
    expect(JSON.parse(localStorage.getItem('reposage.tasks')!)[0].mode).toBe('qa')
  })

  it('creates a fix task from failing test ids', async () => {
    const snap = await seedSnapshot()
    const { router } = await mountApp(`/tasks/new?snapshot=${snap}`)
    document.body.querySelector<HTMLInputElement>('input[value=fix]')!.click()
    await until(() => expect(document.body.querySelector('#t-tests')).not.toBeNull())
    set('#t-tests', 'tests/test_http.py::test_retry')
    submit()
    await until(() => expect(router.currentRoute.value.name).toBe('trajectory'))
    await until(() => expect(document.body.querySelector('[data-status=awaiting_approval]')).not.toBeNull())
  })

  it('rejects bad input client-side: short question, flags in test ids, out-of-range budget', async () => {
    const snap = await seedSnapshot()
    const before = backend.tasks.size
    await mountApp(`/tasks/new?snapshot=${snap}`)
    set('#t-q', 'hi'); submit()
    await until(() => expect(text()).toContain('3 to 2000 characters'))
    document.body.querySelector<HTMLInputElement>('input[value=fix]')!.click()
    await until(() => expect(document.body.querySelector('#t-tests')).not.toBeNull())
    set('#t-tests', '--rootdir=/ tests/x.py'); set('#b-max_usd', '99'); submit()
    await until(() => expect(text()).toContain('Each line must be a pytest node id'))
    expect(text()).toContain('Above 0, up to 5')
    expect(backend.tasks.size).toBe(before)
  })

  it('a missing snapshot is reported by the API (404)', async () => {
    await mountApp('/tasks/new?snapshot=bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb')
    set('#t-q', 'Where is it?'); submit()
    await until(() => expect(byTestId('error-state')?.textContent).toContain('not found'))
  })

  it('cancels a running task after confirmation', async () => {
    await mountApp(`/tasks/${ids.queued}`)
    await until(() => expect(byTestId('cancel-task')).not.toBeNull())
    clickTestId('cancel-task')
    await until(() => expect(byTestId('dialog-confirm')).not.toBeNull())
    expect(backend.tasks.get(ids.queued)!.status).toBe('queued')
    clickTestId('dialog-confirm')
    await until(() => expect(document.body.querySelector('[data-status=cancelled]')).not.toBeNull())
    expect(byTestId('cancel-task')).toBeNull()
  })

  it('offers no cancel on a finished task', async () => {
    await mountApp(`/tasks/${ids.qa}`)
    await until(() => expect(byTestId('status-summary')).not.toBeNull())
    expect(byTestId('cancel-task')).toBeNull()
  })
})
