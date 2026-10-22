import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest'
import { vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { ids, PATCH_V1, sha256 } from '@mock/backend'
import { API, backend, sleep, unmountAll, byTestId, clickTestId, mockHandler, mountApp, server, text } from '../helpers/harness'

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())
beforeEach(() => backend.reset())
afterEach(() => {
  unmountAll()
  server.resetHandlers()
})

const waitText = (s: string, timeout = 4000) => vi.waitFor(() => expect(text()).toContain(s), { timeout, interval: 20 })
const waitTid = (id: string, timeout = 4000) =>
  vi.waitFor(() => { if (!byTestId(id)) throw new Error(`no element with data-testid=${id}`) }, { timeout, interval: 20 })
const statusOf = () => document.body.querySelector('[data-status]')?.getAttribute('data-status')

/** Opens the fix task, lets the scripted stream run to the approval gate, and goes to the review page. */
async function toReview() {
  const app = await mountApp(`/tasks/${ids.fix}`)
  await vi.waitFor(() => expect(statusOf()).toBe('awaiting_approval'), { timeout: 4000, interval: 20 })
  await waitText('A patch is waiting for your decision')
  await app.router.push(`/tasks/${ids.fix}/review`)
  await waitTid('approval-panel')
  return app
}

describe('fix flow over a scripted SSE stream', () => {
  it('shows node progress, denied tool calls and budget burn live', async () => {
    await mountApp(`/tasks/${ids.fix}`)
    await vi.waitFor(() => expect(statusOf()).toBe('awaiting_approval'), { timeout: 4000, interval: 20 })

    const state = (n: string) => document.body.querySelector(`[data-node="${n}"]`)?.getAttribute('data-state')
    await vi.waitFor(() => expect(state('verify')).toBe('done'), { timeout: 4000, interval: 20 })
    expect(['plan', 'retrieve', 'explore', 'patch', 'verify'].map(state)).toEqual(Array(5).fill('done'))
    expect(state('approval')).toBe('pending')

    const rows = [...document.body.querySelectorAll('[data-testid="tool-table"] tbody tr')]
    expect(rows).toHaveLength(3)
    const denied = rows.find((r) => r.getAttribute('data-status') === 'denied')
    expect(denied?.textContent).toContain('path_escape')

    expect(byTestId('budget-steps')?.textContent).toMatch(/4\s*\/\s*30/)
    expect(byTestId('budget-tokens')?.textContent).toContain('18,200')
    expect(byTestId('budget-usd')?.textContent).toContain('$0.07')
  })

  it('approves with the pending sha256, then reflects completion', async () => {
    backend.resumeDelayMs = 400
    await toReview()
    const sha = sha256(PATCH_V1)
    expect(byTestId('patch-sha')?.textContent).toBe(sha)

    clickTestId('approve')
    await waitTid('dialog-confirm')
    expect(document.body.textContent).toContain('Approve and apply this patch?')
    clickTestId('dialog-confirm')

    await waitTid('decision-sent')
    expect(backend.approvals).toEqual([expect.objectContaining({ decision: 'approve', patch_sha256: sha, status: 200 })])
    await vi.waitFor(() => expect(statusOf()).toBe('completed'), { timeout: 4000, interval: 20 })
    expect(byTestId('outcome')?.textContent).toBe('patch_applied')
    await waitTid('final-patch')
    expect(text()).toContain('approved and applied')
  })

  it('rejects with a comment and applies nothing', async () => {
    await toReview()
    const input = document.body.querySelector<HTMLInputElement>('#decision-comment')!
    input.value = 'wrong layer'
    input.dispatchEvent(new Event('input'))
    clickTestId('reject')
    await waitTid('dialog-confirm')
    clickTestId('dialog-confirm')
    await vi.waitFor(() => expect(backend.approvals).toHaveLength(1))
    expect(backend.approvals[0]).toMatchObject({ decision: 'reject', patch_sha256: sha256(PATCH_V1), comment: 'wrong layer' })
    await vi.waitFor(() => expect(byTestId('outcome')?.textContent).toBe('patch_rejected'), { timeout: 4000, interval: 20 })
    await waitTid('final-patch')
    expect(text()).toContain('was not applied')
  })

  it('edit: sends the original sha plus the edited diff, then shows the re-verified patch', async () => {
    await toReview()
    clickTestId('edit')
    const ta = await vi.waitFor(() => {
      const el = document.body.querySelector<HTMLTextAreaElement>('#edit-diff')
      expect(el).not.toBeNull()
      return el!
    })
    expect(byTestId('submit-edit')?.hasAttribute('disabled')).toBe(true) // unchanged diff cannot be submitted
    const edited = PATCH_V1.replace('base * 2 ** attempt', 'base * (2 ** attempt)')
    ta.value = edited
    ta.dispatchEvent(new Event('input'))
    await vi.waitFor(() => expect(byTestId('submit-edit')?.hasAttribute('disabled')).toBe(false))
    clickTestId('submit-edit')
    await vi.waitFor(() => expect(backend.approvals).toHaveLength(1))
    expect(backend.approvals[0]).toMatchObject({ decision: 'edit', patch_sha256: sha256(PATCH_V1), edited_diff: edited })
    // the worker re-verifies and asks again with the new hash
    await vi.waitFor(() => expect(byTestId('approval-panel')?.getAttribute('data-sha')).toBe(sha256(edited)), { timeout: 4000, interval: 20 })
    expect(byTestId('decision-sent')).toBeNull()
  })

  it('409 stale patch: blocks the decision, prompts a refetch, and the retry carries the new sha', async () => {
    // Hold the stream right after the first approval request, so the reviewer is genuinely looking at an old patch.
    const frozenEvents = http.get(`${API}/v1/tasks/:id/events`, ({ request }) => {
      const enc = new TextEncoder()
      return new HttpResponse(
        new ReadableStream({
          async start(c) {
            let last = 0
            let held = false
            while (!held && !request.signal.aborted) {
              for (const e of backend.eventsAfter(ids.fix, last)) {
                last = e.seq
                c.enqueue(enc.encode(`id: ${e.seq}\nevent: ${e.type}\ndata: ${JSON.stringify(e.payload)}\n\n`))
                if (e.type === 'approval_requested') held = true
              }
              await sleep(10)
            }
          },
        }),
        { headers: { 'content-type': 'text/event-stream' } },
      )
    })
    server.use(frozenEvents)
    const app = await mountApp(`/tasks/${ids.fix}`)
    await vi.waitFor(() => expect(statusOf()).toBe('awaiting_approval'), { timeout: 4000, interval: 20 })
    await app.router.push(`/tasks/${ids.fix}/review`)
    await waitTid('approval-panel')
    const oldSha = byTestId('approval-panel')!.getAttribute('data-sha')!

    backend.rotatePatch(ids.fix) // agent produced a new patch behind the reviewer's back
    const newSha = backend.tasks.get(ids.fix)!.patch!.sha256
    expect(newSha).not.toBe(oldSha)

    clickTestId('approve')
    await waitTid('dialog-confirm')
    clickTestId('dialog-confirm')

    await vi.waitFor(() => expect(byTestId('stale-detail')).not.toBeNull(), { timeout: 4000, interval: 20 })
    expect(byTestId('stale-detail')?.textContent).toContain('Patch changed or hash mismatch')
    expect(backend.approvals).toEqual([expect.objectContaining({ patch_sha256: oldSha, status: 409 })])
    expect(byTestId('approve')?.hasAttribute('disabled')).toBe(true)

    // Refetch replays the stream (real handler again) and picks up the rotated patch.
    server.resetHandlers()
    server.use(mockHandler)
    const refetch = [...document.body.querySelectorAll('button')].find((b) => b.textContent?.includes('Refetch latest patch'))!
    refetch.click()
    await vi.waitFor(() => expect(byTestId('approval-panel')?.getAttribute('data-sha')).toBe(newSha), { timeout: 4000, interval: 20 })
    expect(byTestId('approve')?.hasAttribute('disabled')).toBe(false)

    clickTestId('approve')
    await waitTid('dialog-confirm')
    clickTestId('dialog-confirm')
    await vi.waitFor(() => expect(backend.approvals).toHaveLength(2))
    expect(backend.approvals.at(-1)).toMatchObject({ decision: 'approve', patch_sha256: newSha, status: 200 })
  })

  it('409 because the task is no longer awaiting approval also forces a refetch', async () => {
    await toReview()
    backend.tasks.get(ids.fix)!.status = 'running'
    clickTestId('approve')
    await waitTid('dialog-confirm')
    clickTestId('dialog-confirm')
    await vi.waitFor(() => expect(byTestId('stale-detail')?.textContent).toContain("not 'awaiting_approval'"), { timeout: 4000, interval: 20 })
  })
})

describe('SSE disconnect and reconnect', () => {
  it('shows the reconnecting banner, resumes with Last-Event-ID and does not duplicate events', async () => {
    backend.dropNextStreamAfter = 3
    await mountApp(`/tasks/${ids.fix}`)
    await vi.waitFor(() => expect(byTestId('connection-banner')?.getAttribute('data-phase')).toBe('reconnecting'), { timeout: 4000, interval: 10 })
    expect(byTestId('connection-banner')?.textContent).toContain('Resuming from the last event')

    await vi.waitFor(() => expect(statusOf()).toBe('awaiting_approval'), { timeout: 6000, interval: 20 })
    await vi.waitFor(() => expect(backend.streamRequests.length).toBeGreaterThanOrEqual(2), { timeout: 4000 })
    expect(backend.streamRequests[0]?.lastEventId).toBeNull()
    expect(backend.streamRequests[1]?.lastEventId).toBe('3')
    await vi.waitFor(() => expect(byTestId('connection-banner')?.getAttribute('data-phase')).toBe('open'), { timeout: 4000 })

    const seqs = [...document.body.querySelectorAll('[data-testid="event-log"] li > span:first-child')].map((s) => s.textContent)
    expect(new Set(seqs).size).toBe(seqs.length)
    expect(seqs).toHaveLength(15)
  }, 15000)
})
