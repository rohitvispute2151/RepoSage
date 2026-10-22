import { test } from '@playwright/test'
import { FIX, QA, resetMock, signedIn } from './helpers'

// Regenerates docs/screenshots/*.png from the scripted mock. Run with: bun run screenshots
test.skip(!process.env.SHOTS, 'only runs via `bun run screenshots`')
test.use({ viewport: { width: 1360, height: 860 } })

test('capture', async ({ page, request }) => {
  await resetMock(request)
  await signedIn(page, 'light')
  const shot = (name: string, full = true) => page.screenshot({ path: `docs/screenshots/${name}.png`, fullPage: full })

  await page.goto('/repos')
  await page.getByLabel('Name').fill('ClauseGuard')
  await page.getByLabel('Source (git URL or path)').fill('https://github.com/example/clauseguard.git')
  await page.getByLabel('Commit SHA').fill('ea28a84')
  await page.getByRole('button', { name: 'Register and index' }).click()
  await page.locator('[data-status=ready]').waitFor({ timeout: 10_000 })
  await shot('1-repositories')

  await page.goto(`/tasks/${FIX}`)
  await page.getByText('A patch is waiting for your decision').waitFor()
  await shot('2-trajectory')

  await page.goto(`/tasks/${FIX}/review`)
  await page.getByTestId('approval-panel').waitFor()
  await shot('3-approval-diff')
  await page.getByRole('tab', { name: 'Test evidence' }).click()
  await shot('4-approval-evidence', false)

  await page.goto(`/tasks/${QA}/answer`)
  await page.getByTestId('answer').waitFor()
  await shot('5-qa-answer')

  await page.goto('/evals/compare?a=run-baseline&b=run-rerank')
  await page.getByTestId('metric-table').waitFor()
  await shot('6-eval-compare')
})
