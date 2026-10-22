import { expect, type Page, type APIRequestContext } from '@playwright/test'

export const MOCK = 'http://127.0.0.1:8788'
export const KEY = 'reposage-dev-key'
export const FIX = '11111111-1111-4111-8111-111111111111'
export const QA = '22222222-2222-4222-8222-222222222222'
export const QA_NOT_FOUND = '23232323-2323-4323-8323-232323232323'

export async function resetMock(request: APIRequestContext) {
  expect((await request.get(`${MOCK}/__mock/reset`)).ok()).toBeTruthy()
}

export async function signedIn(page: Page, theme: 'light' | 'dark' | 'system' = 'light') {
  await page.addInitScript(([k, t]) => {
    localStorage.setItem('reposage.apiKey', k!)
    localStorage.setItem('reposage.theme', t!)
  }, [KEY, theme])
}

export const approvals = async (request: APIRequestContext) => (await (await request.get(`${MOCK}/__mock/approvals`)).json()) as { decision: string; patch_sha256: string; status: number }[]
