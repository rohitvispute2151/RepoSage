import { expect, test } from '@playwright/test'
import { FIX, KEY, MOCK, QA, QA_NOT_FOUND, approvals, resetMock, signedIn } from './helpers'

test.beforeEach(async ({ request }) => resetMock(request))

test('golden path: open task, watch it run, review the patch, approve, see completion', async ({ page, request }) => {
  // Start from the home page like a real user: key + task id.
  await page.goto('/')
  await page.getByLabel('API key').fill(KEY)
  await page.getByLabel('Task id').fill(FIX)
  await page.getByRole('button', { name: 'Open task' }).click()

  await expect(page.getByRole('heading', { level: 1 })).toContainText(FIX)
  await expect(page.getByText('Awaiting approval').first()).toBeVisible()

  // Trajectory: nodes, a denied tool call with its reason, and budget burn.
  await expect(page.locator('[data-node=verify]')).toHaveAttribute('data-state', 'done')
  await expect(page.locator('[data-node=approval]')).toHaveAttribute('data-state', 'pending')
  await expect(page.getByRole('row', { name: /read_file.*denied.*path_escape/ })).toBeVisible()
  await expect(page.getByTestId('budget-steps')).toContainText('4 / 30')
  await expect(page.getByTestId('budget-usd')).toContainText('$0.07 / $1.00')

  // Review
  await page.getByRole('link', { name: 'Review patch' }).first().click()
  await expect(page.getByRole('heading', { name: 'Proposed patch' })).toBeVisible()
  await expect(page.getByTestId('diff-viewer')).toContainText('return base * 2 ** attempt')
  await page.getByRole('tab', { name: 'Test evidence' }).click()
  await expect(page.getByTestId('test-evidence')).toContainText('Pass on the patched copy')

  // Hostile repo text in the diff and rationale stayed inert.
  expect(await page.evaluate(() => (window as unknown as { __pwned?: number }).__pwned)).toBeUndefined()
  await expect(page.locator('main img, main script')).toHaveCount(0)

  const sha = (await page.getByTestId('patch-sha').textContent())!
  await page.getByRole('button', { name: 'Approve…' }).click()
  await page.getByRole('button', { name: 'Approve and apply' }).click()

  await expect(page.getByText('Completed').first()).toBeVisible()
  await expect(page.getByTestId('outcome')).toHaveText('patch_applied')
  await expect(page.getByText('approved and applied')).toBeVisible()
  expect(await approvals(request)).toEqual([expect.objectContaining({ decision: 'approve', patch_sha256: sha, status: 200 })])
})

test('from a cold start: register a repo, create a question task, read the answer, cancel another', async ({ page }) => {
  await signedIn(page)
  await page.goto('/')
  await expect(page.getByTestId('api-status')).toContainText('Database ready')
  await page.getByRole('link', { name: /Register a repository/ }).click()
  await page.getByLabel('Name').fill('svc')
  await page.getByLabel('Source (git URL or path)').fill('https://example.com/svc.git')
  await page.getByLabel('Commit SHA').fill('3c47104')
  await page.getByRole('button', { name: 'Register and index' }).click()
  await expect(page.locator('[data-status=ready]')).toBeVisible({ timeout: 10_000 })
  await page.getByRole('button', { name: 'Start a task on this snapshot' }).click()

  await page.getByLabel('Question', { exact: true }).fill('Where is retry backoff computed?')
  await page.getByRole('button', { name: 'Create task' }).click()
  await expect(page.getByTestId('outcome')).toHaveText('answered', { timeout: 10_000 })
  await page.getByRole('link', { name: 'Answer' }).click()
  await expect(page.getByTestId('citations').getByText('src/pkg/http.py:38-44')).toBeVisible()

  // A second, fix-mode task stops at the approval gate; cancelling it discards the patch.
  await page.goto('/tasks/new')
  await page.getByLabel('Fix failing tests').check()
  await page.getByLabel(/Failing tests/).fill('tests/test_http.py::test_retry')
  await page.getByRole('button', { name: 'Create task' }).click()
  await expect(page.getByText('Awaiting approval').first()).toBeVisible({ timeout: 10_000 })
  await page.getByRole('button', { name: 'Cancel task' }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Cancel task' }).click()
  await expect(page.getByText('Cancelled').first()).toBeVisible()
  await page.goto('/')
  await expect(page.getByTestId('recent-tasks').locator('li')).toHaveCount(2)
})

test('keyboard only: approval is fully operable without a mouse', async ({ page, request }) => {
  await signedIn(page)
  await page.goto(`/tasks/${FIX}/review`)
  await expect(page.getByTestId('approval-panel')).toBeVisible()

  const focusedTestId = () => page.evaluate(() => document.activeElement?.getAttribute('data-testid') ?? '')
  const tabTo = async (testId: string) => {
    for (let i = 0; i < 60; i++) {
      if ((await focusedTestId()) === testId) return
      await page.keyboard.press('Tab')
    }
    throw new Error(`could not reach ${testId} by keyboard`)
  }

  // Tabs are arrow-key navigable.
  await page.getByRole('tab', { name: 'Diff' }).focus()
  await page.keyboard.press('ArrowRight')
  await expect(page.getByRole('tab', { name: 'Test evidence' })).toBeFocused()
  await expect(page.getByRole('tab', { name: 'Test evidence' })).toHaveAttribute('data-state', 'active')

  // Reach Approve, open the dialog with Enter.
  await tabTo('approve')
  await page.keyboard.press('Enter')
  const dialog = page.getByRole('dialog', { name: 'Approve and apply this patch?' })
  await expect(dialog).toBeVisible()

  // Focus is trapped in the dialog.
  for (let i = 0; i < 6; i++) {
    await page.keyboard.press('Tab')
    expect(await page.evaluate(() => !!document.activeElement?.closest('[role=dialog]'))).toBe(true)
  }
  // Escape closes it and returns focus to the trigger.
  await page.keyboard.press('Escape')
  await expect(dialog).toBeHidden()
  await expect(page.getByTestId('approve')).toBeFocused()

  // Re-open and confirm, again by keyboard.
  await page.keyboard.press('Enter')
  await expect(dialog).toBeVisible()
  await tabTo('dialog-confirm')
  await page.keyboard.press('Enter')

  await expect(page.getByTestId('outcome')).toHaveText('patch_applied')
  const done = await approvals(request)
  expect(done).toHaveLength(1)
  expect(done[0]).toMatchObject({ decision: 'approve', status: 200 })
})

test('stale patch: 409 blocks the decision and prompts a refetch', async ({ page, request }) => {
  await signedIn(page)
  // Freeze the live stream at the first approval request so this reviewer holds an old patch.
  await page.route('**/v1/tasks/*/events', async (route) => {
    const events = (await (await request.get(`${MOCK}/__mock/events/${FIX}`)).json()) as { seq: number; type: string; payload: unknown }[]
    const upto = events.findIndex((e) => e.type === 'approval_requested')
    const body = events.slice(0, upto + 1).map((e) => `id: ${e.seq}\nevent: ${e.type}\ndata: ${JSON.stringify(e.payload)}\n\n`).join('')
    await route.fulfill({ status: 200, headers: { 'content-type': 'text/event-stream' }, body })
  })
  await page.goto(`/tasks/${FIX}/review`)
  await expect(page.getByTestId('approval-panel')).toBeVisible()
  const oldSha = (await page.getByTestId('patch-sha').textContent())!

  await request.get(`${MOCK}/__mock/rotate-patch/${FIX}`)
  await page.getByRole('button', { name: 'Approve…' }).click()
  await page.getByRole('button', { name: 'Approve and apply' }).click()

  const stale = page.getByRole('dialog', { name: 'This patch is out of date' })
  await expect(stale).toBeVisible()
  await expect(stale).toContainText('Patch changed or hash mismatch')
  expect((await approvals(request))[0]).toMatchObject({ patch_sha256: oldSha, status: 409 })

  await page.unroute('**/v1/tasks/*/events')
  await stale.getByRole('button', { name: 'Refetch latest patch' }).click()
  await expect(page.getByTestId('patch-sha')).not.toHaveText(oldSha)
  await expect(page.getByRole('button', { name: 'Approve…' })).toBeEnabled()
})

test('SSE drop: banner shows, stream resumes from Last-Event-ID without losing or duplicating events', async ({ page, request }) => {
  await signedIn(page)
  await request.get(`${MOCK}/__mock/drop-next-stream?after=3`)
  await page.goto(`/tasks/${FIX}`)
  await expect(page.getByTestId('connection-banner')).toContainText('Reconnecting')
  await expect(page.getByText('Awaiting approval').first()).toBeVisible({ timeout: 10_000 })
  const streams = (await (await request.get(`${MOCK}/__mock/streams`)).json()) as { lastEventId: string | null }[]
  expect(streams[0]?.lastEventId).toBeNull()
  expect(streams[1]?.lastEventId).toBe('3')
  const seqs = await page.locator('[data-testid=event-log] li > span:first-child').allTextContents()
  expect(new Set(seqs).size).toBe(seqs.length)
  expect(seqs).toHaveLength(15)
})

test('QA: answer with linked-location citations, and a clear not-found state', async ({ page }) => {
  await signedIn(page)
  await page.goto(`/tasks/${QA}/answer`)
  await expect(page.getByTestId('answer-text')).toContainText('compute_backoff')
  await expect(page.getByTestId('citations').getByText('src/pkg/http.py:38-44')).toBeVisible()
  await expect(page.locator('main img')).toHaveCount(0)
  expect(await page.evaluate(() => (window as unknown as { __pwned?: number }).__pwned)).toBeUndefined()

  await page.goto(`/tasks/${QA_NOT_FOUND}/answer`)
  await expect(page.getByTestId('not-found')).toContainText('could not find an answer')
})

test('eval compare: paired deltas and spread', async ({ page }) => {
  await signedIn(page)
  await page.goto('/evals/compare?a=run-baseline&b=run-rerank')
  const recall = page.locator('[data-metric=recall_at_5]')
  await expect(recall).toHaveAttribute('data-verdict', 'improved')
  await expect(recall).toContainText('±')
  await expect(page.locator('[data-metric=mrr]')).toHaveAttribute('data-verdict', 'within-noise')
})
