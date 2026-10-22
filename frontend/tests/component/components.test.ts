import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import StatusBadge from '@/components/StatusBadge.vue'
import ConnectionBanner from '@/components/ConnectionBanner.vue'
import BudgetPanel from '@/components/BudgetPanel.vue'
import { TASK_STATUSES } from '@/api/contracts'
import type { ConnectionState } from '@/lib/sse'

describe('StatusBadge', () => {
  it.each(TASK_STATUSES)('renders %s with a text label (not colour alone)', (s) => {
    const w = mount(StatusBadge, { props: { status: s } })
    expect(w.attributes('data-status')).toBe(s)
    expect(w.text().length).toBeGreaterThan(3)
  })
})

describe('ConnectionBanner', () => {
  const states: [ConnectionState, RegExp, boolean][] = [
    [{ phase: 'connecting' }, /Connecting/, false],
    [{ phase: 'open' }, /Live/, false],
    [{ phase: 'reconnecting', attempt: 2, delayMs: 2000, reason: 'fetch failed' }, /Reconnecting in 2s, attempt 2/, false],
    [{ phase: 'closed' }, /Stream finished/, false],
    [{ phase: 'failed', reason: 'Gave up', fatal: false, status: null }, /Gave up/, true],
    [{ phase: 'failed', reason: 'Stream rejected (HTTP 401)', fatal: true, status: 401 }, /Not retrying/, false],
  ]
  it.each(states)('%j', (state, re, hasRetry) => {
    const w = mount(ConnectionBanner, { props: { state } })
    expect(w.text()).toMatch(re)
    expect(w.find('button').exists()).toBe(hasRetry)
  })
  it('offers manual reconnect after giving up', async () => {
    const w = mount(ConnectionBanner, { props: { state: { phase: 'failed', reason: 'x', fatal: false, status: null } } })
    await w.get('button').trigger('click')
    expect(w.emitted('retry')).toHaveLength(1)
  })
})

describe('BudgetPanel', () => {
  const base = { limits: { max_steps: 30, max_tokens: 1000, max_usd: 1, max_seconds: 100 }, source: 'stream' as const }
  it('shows used / limit for steps, tokens, USD and seconds', () => {
    const w = mount(BudgetPanel, { props: { ...base, usage: { steps: 3, tokens: 500, usd: 0.25, seconds: 40 } } })
    expect(w.get('[data-testid=budget-steps]').text()).toMatch(/3\s*\/\s*30/)
    expect(w.get('[data-testid=budget-tokens]').text()).toMatch(/500\s*\/\s*1,000/)
    expect(w.get('[data-testid=budget-usd]').text()).toContain('$0.25')
    expect(w.get('[data-testid=budget-seconds]').text()).toMatch(/40s\s*\/\s*100s/)
    w.unmount()
  })
  it('warns at 85% and says what was derived', () => {
    const w = mount(BudgetPanel, { props: { ...base, source: 'derived', usage: { steps: 26 } } })
    expect(w.get('[data-testid=budget-steps]').text()).toContain('Over 85%')
    expect(w.get('[data-testid=budget-tokens]').text()).toContain('not reported')
    w.unmount()
  })
})
