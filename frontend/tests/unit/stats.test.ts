import { describe, expect, it } from 'vitest'
import type { EvalRunExport } from '@/api/contracts'
import { compareRuns, sampleSd } from '@/lib/stats'
import { evalRuns } from '@mock/backend'

const run = (id: string, rows: [string, number, number][]): EvalRunExport => ({
  run: { id, config_fingerprint: id },
  results: rows.map(([case_id, repeat_idx, v]) => ({ case_id, repeat_idx, metrics: { m: v } })),
})

describe('compareRuns', () => {
  it('pairs per case, and counts wins, losses and ties', () => {
    const a = run('a', [['c1', 0, 0.5], ['c2', 0, 0.5], ['c3', 0, 0.5]])
    const b = run('b', [['c1', 0, 0.9], ['c2', 0, 0.1], ['c3', 0, 0.5]])
    const m = compareRuns(a, b).metrics[0]!
    expect([m.wins, m.losses, m.ties]).toEqual([1, 1, 1])
    expect(m.meanDelta).toBeCloseTo(0)
  })

  it('does not claim a verdict with a single repeat (no spread to compare against)', () => {
    const m = compareRuns(run('a', [['c1', 0, 0.1]]), run('b', [['c1', 0, 0.9]])).metrics[0]!
    expect(m.verdict).toBe('unknown')
    expect(Number.isNaN(m.spreadA)).toBe(true)
  })

  it('computes spread as the sd of per-repeat means', () => {
    const a = run('a', [['c1', 0, 0.4], ['c1', 1, 0.6], ['c1', 2, 0.5]])
    expect(compareRuns(a, a).metrics[0]!.spreadA).toBeCloseTo(sampleSd([0.4, 0.6, 0.5]))
  })

  it('calls a delta inside run-to-run spread "within-noise"', () => {
    const a = run('a', [['c1', 0, 0.4], ['c1', 1, 0.6]])
    const b = run('b', [['c1', 0, 0.45], ['c1', 1, 0.65]])
    expect(compareRuns(a, b).metrics[0]!.verdict).toBe('within-noise')
  })

  it('excludes unpaired cases and reports them', () => {
    const c = compareRuns(run('a', [['c1', 0, 1], ['only-a', 0, 1]]), run('b', [['c1', 0, 1], ['only-b', 0, 1]]))
    expect(c.pairedCases).toBe(1)
    expect(c.onlyInA).toEqual(['only-a'])
    expect(c.onlyInB).toEqual(['only-b'])
  })

  it('on the fixtures: recall improves beyond noise, MRR does not', () => {
    const c = compareRuns(evalRuns['run-baseline']!, evalRuns['run-rerank']!)
    const by = Object.fromEntries(c.metrics.map((m) => [m.metric, m]))
    expect(by.recall_at_5?.verdict).toBe('improved')
    expect(by.mrr?.verdict).toBe('within-noise')
    expect(c.onlyInA).toHaveLength(1) // the candidate run dropped a case
  })
})
