import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'
import { FIX, QA, QA_NOT_FOUND, resetMock, signedIn } from './helpers'

test.beforeEach(async ({ request }) => resetMock(request))

async function audit(page: Page, label: string) {
  const { violations } = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'best-practice']).analyze()
  const blocking = violations.filter((v) => v.impact === 'serious' || v.impact === 'critical')
  expect(blocking.map((v) => `${label}: ${v.id} (${v.impact}) ${v.nodes.map((n) => n.target.join(' ')).join(' | ')}`)).toEqual([])
  // Stricter than required: minor/moderate findings are also kept at zero so regressions are visible.
  expect(violations.map((v) => `${label}: ${v.id} (${v.impact})`)).toEqual([])
}

for (const theme of ['light', 'dark'] as const) {
  test.describe(`axe, ${theme} theme, real colour contrast`, () => {
    test.beforeEach(async ({ page }) => signedIn(page, theme))

    test('home', async ({ page }) => {
      await page.goto('/')
      await expect(page.getByRole('heading', { name: 'Open a task' })).toBeVisible()
      await audit(page, 'home')
    })

    test('repositories and new task', async ({ page }) => {
      await page.goto('/repos')
      await expect(page.getByRole('heading', { name: 'Repositories' })).toBeVisible()
      await audit(page, 'repos-empty')
      await page.getByLabel('Name').fill('svc')
      await page.getByLabel('Source (git URL or path)').fill('https://example.com/svc.git')
      await page.getByLabel('Commit SHA').fill('3c47104')
      await page.getByRole('button', { name: 'Register and index' }).click()
      await expect(page.locator('[data-status=ready]')).toBeVisible({ timeout: 10_000 })
      await audit(page, 'repos-ready')
      await page.getByRole('link', { name: 'New task' }).click()
      await expect(page.getByRole('heading', { name: 'New task' })).toBeVisible()
      await audit(page, 'new-task-qa')
      await page.getByLabel('Fix failing tests').check()
      await page.getByRole('button', { name: 'Create task' }).click()
      await expect(page.getByRole('alert').first()).toBeVisible()
      await audit(page, 'new-task-fix-errors')
    })

    test('trajectory awaiting approval', async ({ page }) => {
      await page.goto(`/tasks/${FIX}`)
      await expect(page.getByText('A patch is waiting for your decision')).toBeVisible()
      await audit(page, 'trajectory')
    })

    test('review, every tab, and the approve dialog', async ({ page }) => {
      await page.goto(`/tasks/${FIX}/review`)
      await expect(page.getByTestId('approval-panel')).toBeVisible()
      await audit(page, 'review/diff')
      await page.getByRole('tab', { name: 'Test evidence' }).click()
      await audit(page, 'review/tests')
      await page.getByRole('tab', { name: 'Rationale' }).click()
      await audit(page, 'review/rationale')
      await page.getByRole('button', { name: 'Approve…' }).click()
      await expect(page.getByRole('dialog')).toBeVisible()
      await audit(page, 'review/dialog')
    })

    test('answer, not found, and eval compare', async ({ page }) => {
      await page.goto(`/tasks/${QA}/answer`)
      await expect(page.getByTestId('answer')).toBeVisible()
      await audit(page, 'answer')
      await page.goto(`/tasks/${QA_NOT_FOUND}/answer`)
      await expect(page.getByTestId('not-found')).toBeVisible()
      await audit(page, 'not-found')
      await page.goto('/evals/compare?a=run-baseline&b=run-rerank')
      await expect(page.getByTestId('metric-table')).toBeVisible()
      await audit(page, 'eval-compare')
    })
  })
}
