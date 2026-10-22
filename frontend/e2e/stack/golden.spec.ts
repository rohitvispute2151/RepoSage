import { expect, test } from '@playwright/test'

/**
 * Golden path against the real docker-compose stack.
 *
 * Preconditions (all must hold, otherwise the test is skipped with the reason, never silently passed):
 *  - the API answers on API_URL (default http://127.0.0.1:8000) and accepts API_KEY (default reposage-dev-key),
 *  - STACK_TASK_ID names a *fix* task that is in awaiting_approval.
 * Create one with POST /v1/repos then POST /v1/tasks {mode:"fix"} and wait for the worker (see README).
 */
const API = process.env.API_URL ?? 'http://127.0.0.1:8000'
const KEY = process.env.API_KEY ?? 'reposage-dev-key'
const TASK = process.env.STACK_TASK_ID

test('golden path against the compose stack', async ({ page, request }) => {
  const health = await request.get(`${API}/healthz`, { timeout: 3000 }).catch(() => null)
  test.skip(!health?.ok(), `RepoSage API not reachable at ${API}: start the stack first`)
  test.skip(!TASK, 'STACK_TASK_ID not set: need a fix task awaiting approval')

  const task = await request.get(`${API}/v1/tasks/${TASK}`, { headers: { 'X-API-Key': KEY } })
  expect(task.ok(), 'task lookup').toBeTruthy()
  test.skip((await task.json()).status !== 'awaiting_approval', 'task is not awaiting approval')

  await page.addInitScript((k) => localStorage.setItem('reposage.apiKey', k), KEY)
  await page.goto(`/tasks/${TASK}/review`)
  await expect(page.getByRole('heading', { name: 'Proposed patch' })).toBeVisible({ timeout: 15_000 })
  const sha = await page.getByTestId('patch-sha').textContent()
  await page.getByRole('button', { name: 'Approve…' }).click()
  await page.getByRole('button', { name: 'Approve and apply' }).click()
  await expect(page.getByText('Decision sent')).toBeVisible()
  expect(sha).toMatch(/^[0-9a-f]{64}$/)
})
