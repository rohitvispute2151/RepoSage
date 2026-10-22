/**
 * Invariant (a): the UI never records an approval decision without sending the current patch_sha256, and offers
 * no way to apply a patch except through an approval request on a pending patch.
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { createPinia } from 'pinia'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { mount } from '@vue/test-utils'
import ApprovalPanel from '@/components/ApprovalPanel.vue'
import { submitApproval } from '@/api/tasks'
import type { PendingPatch } from '@/stores/trajectory'
import { API, byTestId, clickTestId, server } from '../helpers/harness'

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())

const SHA_1 = 'a'.repeat(64)
const SHA_2 = 'b'.repeat(64)
const pendingFor = (sha: string) =>
  ({ patch_id: 'p1', diff: 'diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n@@ -1,1 +1,1 @@\n-a\n+b\n', sha256: sha, test_evidence: { all_target_pass: true, regressions: 0, policy_ok: true, failure_digest: '' }, rationale: 'r', seq: 4 }) as unknown as PendingPatch

let bodies: Record<string, unknown>[] = []
server.use(
  http.post(`${API}/v1/tasks/:id/approval`, async ({ request }) => {
    bodies.push((await request.json()) as Record<string, unknown>)
    return HttpResponse.json({ status: 'accepted' })
  }),
)
afterEach(() => {
  bodies = []
  document.body.innerHTML = ''
})

function mountPanel(sha: string, canDecide = true) {
  return mount(ApprovalPanel, {
    attachTo: document.body,
    props: { taskId: '11111111-1111-4111-8111-111111111111', pending: pendingFor(sha), canDecide, blockedReason: 'not awaiting' },
    global: { plugins: [createPinia(), [VueQueryPlugin, { queryClient: new QueryClient({ defaultOptions: { queries: { retry: false } } }) }]] },
  })
}
const confirm = async () => {
  await vi.waitFor(() => expect(byTestId('dialog-confirm')).not.toBeNull())
  clickTestId('dialog-confirm')
}

describe('approval always carries the pending patch hash', () => {
  it('approve', async () => {
    mountPanel(SHA_1)
    clickTestId('approve')
    await confirm()
    await vi.waitFor(() => expect(bodies).toHaveLength(1))
    expect(bodies[0]).toMatchObject({ decision: 'approve', patch_sha256: SHA_1 })
  })

  it('reject', async () => {
    mountPanel(SHA_1)
    clickTestId('reject')
    await confirm()
    await vi.waitFor(() => expect(bodies).toHaveLength(1))
    expect(bodies[0]).toMatchObject({ decision: 'reject', patch_sha256: SHA_1 })
  })

  it('edit', async () => {
    mountPanel(SHA_1)
    clickTestId('edit')
    const ta = await vi.waitFor(() => {
      const el = document.body.querySelector<HTMLTextAreaElement>('#edit-diff')
      expect(el).not.toBeNull()
      return el!
    })
    ta.value = 'changed'
    ta.dispatchEvent(new Event('input'))
    await vi.waitFor(() => expect(byTestId('submit-edit')?.hasAttribute('disabled')).toBe(false))
    clickTestId('submit-edit')
    await vi.waitFor(() => expect(bodies).toHaveLength(1))
    expect(bodies[0]).toMatchObject({ decision: 'edit', patch_sha256: SHA_1, edited_diff: 'changed' })
  })

  it('uses the new hash once the pending patch changes, never the old one', async () => {
    const w = mountPanel(SHA_1)
    await w.setProps({ pending: pendingFor(SHA_2) })
    clickTestId('approve')
    await confirm()
    await vi.waitFor(() => expect(bodies).toHaveLength(1))
    expect(bodies[0]?.patch_sha256).toBe(SHA_2)
  })

  it('sends nothing when decisions are disabled', async () => {
    mountPanel(SHA_1, false)
    clickTestId('approve')
    clickTestId('reject')
    clickTestId('edit')
    await new Promise((r) => setTimeout(r, 100))
    expect(byTestId('dialog-confirm')).toBeNull()
    expect(bodies).toHaveLength(0)
  })

  it('submitApproval refuses a pending patch with no hash', async () => {
    const empty = { ...pendingFor(''), sha256: '' } as unknown as PendingPatch
    await expect(submitApproval('t', empty, { decision: 'approve' })).rejects.toThrow(/refusing/)
    expect(bodies).toHaveLength(0)
  })

  it('cannot be called with a hand-built patch (compile-time brand)', () => {
    // @ts-expect-error a plain object is not a PendingPatch: only an approval_requested event can produce one
    const call = () => submitApproval('t', { sha256: SHA_1, diff: '' }, { decision: 'approve' })
    expect(call).toBeTypeOf('function')
  })
})

describe('no route to applying a patch without an approval request', () => {
  const walk = (dir: string): string[] =>
    readdirSync(dir).flatMap((f) => (statSync(join(dir, f)).isDirectory() ? walk(join(dir, f)) : [join(dir, f)]))
  const files = walk('src').filter((f) => /\.(ts|vue)$/.test(f) && !f.endsWith('schema.d.ts'))
  const src = (f: string) => readFileSync(f, 'utf8')

  it('the approval endpoint is reachable from exactly one module; other POSTs are create/cancel/register only', () => {
    const posted = files.flatMap((f) => [...src(f).matchAll(/api\.POST\('([^']+)'/g)].map((m) => m[1]))
    expect(posted.sort()).toEqual(['/v1/repos', '/v1/tasks', '/v1/tasks/{task_id}/approval', '/v1/tasks/{task_id}/cancel'])
    expect(files.filter((f) => /method:\s*['"](POST|PUT|PATCH|DELETE)/.test(src(f)))).toEqual([])
    const approvalPath = files.filter((f) => src(f).includes('/approval'))
    expect(approvalPath).toEqual([join('src', 'api', 'tasks.ts')])
  })

  it('submitApproval is only called from the approval panel', () => {
    const callers = files.filter((f) => /submitApproval\(/.test(src(f)) && !f.endsWith('tasks.ts'))
    expect(callers).toEqual([join('src', 'components', 'ApprovalPanel.vue')])
  })

  it('the approval panel is only rendered for a pending patch coming from the event stream', () => {
    const users = files.filter((f) => src(f).includes('<ApprovalPanel'))
    expect(users).toEqual([join('src', 'views', 'ReviewView.vue')])
    expect(src(join('src', 'views', 'ReviewView.vue'))).toMatch(/v-else-if="store\.pendingPatch"/)
  })
})
