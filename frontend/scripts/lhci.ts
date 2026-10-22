/** Runs Lighthouse CI with Playwright's Chromium so no system Chrome is required. */
import { chromium } from '@playwright/test'

const chromePath = chromium.executablePath()
const proc = Bun.spawn(['bunx', 'lhci', 'autorun', ...process.argv.slice(2)], {
  env: { ...process.env, CHROME_PATH: chromePath },
  stdout: 'inherit',
  stderr: 'inherit',
})
process.exit(await proc.exited)
