/**
 * Invariant (b): repo text, tool output and model output are never rendered as HTML.
 * A static scan bans the sinks; runtime tests feed hostile payloads through every component that shows them.
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia } from 'pinia'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { mount } from '@vue/test-utils'
import { h } from 'vue'
import ApprovalPanel from '@/components/ApprovalPanel.vue'
import CitationList from '@/components/CitationList.vue'
import DiffViewer from '@/components/DiffViewer.vue'
import TestEvidence from '@/components/TestEvidence.vue'
import ToolCallList from '@/components/ToolCallList.vue'
import type { PendingPatch } from '@/stores/trajectory'
import { HOSTILE, ids } from '@mock/backend'
import { backend, byTestId, mountApp, server, text, unmountAll } from '../helpers/harness'

declare global { interface Window { __pwned?: number } }

const walk = (dir: string): string[] =>
  readdirSync(dir).flatMap((f) => (statSync(join(dir, f)).isDirectory() ? walk(join(dir, f)) : [join(dir, f)]))

/** Anything that proves markup was parsed out of text: injected elements or inline handlers. */
// The console's own icons are SVG. They are authored in AppIcon.vue / BrandMark.vue, carry `data-app-svg`, and may contain
// only these drawing elements. An <svg> without the marker, or with anything else inside, is still treated as injected.
const DRAWING = new Set(['path', 'circle', 'rect', 'defs', 'lineargradient', 'stop'])
function markupFindings(root: ParentNode): string[] {
  const found: string[] = []
  root.querySelectorAll('script, img, svg, iframe, object, embed, link[rel=stylesheet], base, meta[http-equiv]').forEach((e) => {
    const own = e.tagName.toLowerCase() === 'svg' && e.hasAttribute('data-app-svg') && [...e.querySelectorAll('*')].every((c) => DRAWING.has(c.tagName.toLowerCase()))
    if (!own) found.push(`<${e.tagName.toLowerCase()}>`)
  })
  root.querySelectorAll('svg[data-app-svg] *').forEach((e) => { if (!DRAWING.has(e.tagName.toLowerCase())) found.push(`<${e.tagName.toLowerCase()}> inside app svg`) })
  root.querySelectorAll('*').forEach((e) => {
    for (const a of e.getAttributeNames()) if (/^on/i.test(a)) found.push(`${e.tagName.toLowerCase()}[${a}]`)
    for (const a of ['href', 'src', 'action', 'formaction']) if (/^\s*javascript:/i.test(e.getAttribute(a) ?? '')) found.push(`${a}=javascript:`)
  })
  return found
}

describe('static: HTML sinks are banned from src/', () => {
  const files = walk('src').filter((f) => /\.(ts|vue)$/.test(f) && !f.endsWith('schema.d.ts'))
  const sinks = [/v-html/, /\binnerHTML\b/, /\bouterHTML\b/, /insertAdjacentHTML/, /document\.write/, /createContextualFragment/, /DOMParser/, /\bsrcdoc\b/, /<component\s+:is=/, /\beval\(/, /new Function\(/]
  it.each(sinks.map((s) => [String(s), s] as const))('no use of %s', (_n, re) => {
    expect(files.filter((f) => re.test(readFileSync(f, 'utf8')))).toEqual([])
  })
  it('no markdown renderer is a dependency', () => {
    const pkg = JSON.parse(readFileSync('package.json', 'utf8')) as { dependencies: Record<string, string> }
    expect(Object.keys(pkg.dependencies).filter((d) => /marked|markdown|showdown|remark|highlight|prism|shiki/.test(d))).toEqual([])
  })
})

describe('the detector itself', () => {
  it('flags text that was injected as HTML (so a regression would fail the suite)', () => {
    const w = mount({ render: () => h('div', { innerHTML: HOSTILE }) }, { attachTo: document.body })
    expect(markupFindings(w.element)).toEqual(expect.arrayContaining(['<img>', '<script>', '<svg>', 'img[onerror]']))
    w.unmount()
  })
})

describe('the detector and the app-icon exemption', () => {
  const render = (html: string) => { const w = mount({ render: () => h('div', { innerHTML: html }) }, { attachTo: document.body }); const f = markupFindings(w.element); w.unmount(); return f }
  it('accepts a marked svg that only draws', () => {
    expect(render('<svg data-app-svg><path d="M0 0"/></svg>')).toEqual([])
  })
  it('still flags an unmarked svg, even a harmless-looking one', () => {
    expect(render('<svg><path d="M0 0"/></svg>')).toEqual(['<svg>'])
  })
  it('flags script, foreignObject or handlers hidden inside a marked svg', () => {
    expect(render('<svg data-app-svg><script>1</script></svg>')).toEqual(expect.arrayContaining(['<svg>']))
    expect(render('<svg data-app-svg><foreignObject><div>x</div></foreignObject></svg>')).not.toEqual([])
    expect(render('<svg data-app-svg onload="x()"><path d="M0 0"/></svg>')).toEqual(['svg[onload]'])
  })
})

describe('runtime: hostile payloads stay inert text', () => {
  beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
  afterAll(() => server.close())
  beforeEach(() => { backend.reset(); window.__pwned = undefined })
  afterEach(() => { unmountAll(); document.body.innerHTML = '' })

  const expectInert = (root: ParentNode, needle = '<img src=x') => {
    expect(markupFindings(root)).toEqual([])
    expect(window.__pwned).toBeUndefined()
    expect(root.textContent).toContain(needle)
  }

  it('DiffViewer', () => {
    const diff = `diff --git a/${HOSTILE} b/${HOSTILE}\n--- a/x\n+++ b/x\n@@ -1,1 +1,1 @@\n-${HOSTILE}\n+${HOSTILE}\n`
    const w = mount(DiffViewer, { props: { diff }, attachTo: document.body })
    expectInert(w.element)
  })

  it('ToolCallList (tool name, denial reason)', () => {
    const w = mount(ToolCallList, { props: { calls: [{ key: '1', seq: 1, tool: HOSTILE, status: 'denied', denialReason: HOSTILE, durationMs: 1, node: HOSTILE }] }, attachTo: document.body })
    expectInert(w.element)
  })

  it('CitationList (path, symbol), including a source-link template', () => {
    const w = mount(CitationList, { props: { citations: [{ path: HOSTILE, start_line: 1, end_line: 2, symbol: HOSTILE }] }, attachTo: document.body })
    expectInert(w.element)
  })

  it('TestEvidence (digest, log tail, test ids)', () => {
    const w = mount(TestEvidence, { props: { evidence: { all_target_pass: false, regressions: 1, policy_ok: true, failure_digest: HOSTILE, log_tail: HOSTILE, tests: [{ id: HOSTILE, outcome: HOSTILE }] } }, attachTo: document.body })
    expectInert(w.element)
  })

  it('ApprovalPanel (diff, rationale, evidence, patch hash) including its dialogs', async () => {
    const pending = { patch_id: 'p', diff: `--- a/x\n+++ b/x\n@@ -1 +1 @@\n-${HOSTILE}\n+${HOSTILE}\n`, sha256: HOSTILE, rationale: HOSTILE, test_evidence: { all_target_pass: true, regressions: 0, policy_ok: true, failure_digest: HOSTILE }, seq: 1 } as unknown as PendingPatch
    const w = mount(ApprovalPanel, {
      props: { taskId: ids.fix, pending, canDecide: true },
      attachTo: document.body,
      global: { plugins: [createPinia(), [VueQueryPlugin, { queryClient: new QueryClient() }]] },
    })
    byTestId('approve')!.click()
    await vi.waitFor(() => expect(byTestId('dialog-confirm')).not.toBeNull())
    expectInert(document.body)
    w.unmount()
  })

  it('QA answer, citation paths and verifier notes (full app)', async () => {
    await mountApp(`/tasks/${ids.qa}/answer`)
    await vi.waitFor(() => expect(byTestId('answer')).not.toBeNull())
    expectInert(document.body)
    expect(text()).toContain('src/pkg/<b>client</b>.py')
    expect(document.body.querySelector('b')).toBeNull()
  })

  it('event log with hostile node names and error text (full app)', async () => {
    backend.tasks.get(ids.queued)!.events.push(
      { seq: 1, type: 'node_started', payload: { node: HOSTILE } },
      { seq: 2, type: 'tool_call', payload: { tool: HOSTILE, status: 'denied', denial_reason: HOSTILE } },
      { seq: 3, type: 'patch_applied', payload: { applied: false, error: HOSTILE } },
    )
    await mountApp(`/tasks/${ids.queued}`)
    await vi.waitFor(() => expect(byTestId('event-log')).not.toBeNull())
    expectInert(document.body)
  })

  it('eval compare labels and case ids (full app)', async () => {
    await mountApp('/evals/compare?a=run-hostile&b=run-hostile')
    await vi.waitFor(() => expect(byTestId('metric-table')).not.toBeNull())
    document.body.querySelectorAll('details').forEach((d) => d.setAttribute('open', ''))
    expectInert(document.body)
  })

  it('the home page does not echo a hostile task id back as markup', async () => {
    const { wrapper } = await mountApp('/')
    const input = wrapper.get('#task-id')
    await input.setValue(HOSTILE)
    await wrapper.get('form').trigger('submit')
    expect(markupFindings(document.body)).toEqual([])
  })
})
