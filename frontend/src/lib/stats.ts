import type { EvalRunExport } from '@/api/contracts'

export const mean = (xs: number[]): number => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : NaN)

/** Sample standard deviation (n-1). NaN when fewer than two samples. */
export function sampleSd(xs: number[]): number {
  if (xs.length < 2) return NaN
  const m = mean(xs)
  return Math.sqrt(xs.reduce((a, x) => a + (x - m) ** 2, 0) / (xs.length - 1))
}

function numericMetrics(m: Record<string, unknown>): Record<string, number> {
  const out: Record<string, number> = {}
  for (const [k, v] of Object.entries(m)) {
    if (typeof v === 'number' && Number.isFinite(v)) out[k] = v
    else if (typeof v === 'boolean') out[k] = v ? 1 : 0
  }
  return out
}

export interface PairedCase {
  caseId: string
  a: number
  b: number
  delta: number
  outcome: 'win' | 'loss' | 'tie'
}

export interface MetricComparison {
  metric: string
  meanA: number
  meanB: number
  /** Standard deviation of the run-level mean across repeats (run-to-run spread). NaN with a single repeat. */
  spreadA: number
  spreadB: number
  repeatsA: number
  repeatsB: number
  meanDelta: number
  /** Standard error of the paired per-case delta. NaN with fewer than two paired cases. */
  deltaSe: number
  wins: number
  losses: number
  ties: number
  /** LLD §14.5: improvement only when the paired difference exceeds run-to-run spread. */
  verdict: 'improved' | 'regressed' | 'within-noise' | 'unknown'
  cases: PairedCase[]
}

export interface Comparison {
  metrics: MetricComparison[]
  onlyInA: string[]
  onlyInB: string[]
  pairedCases: number
  sameFingerprint: boolean
}

function perCaseMeans(run: EvalRunExport, metric: string): Map<string, number> {
  const bucket = new Map<string, number[]>()
  for (const r of run.results) {
    const v = numericMetrics(r.metrics)[metric]
    if (v === undefined) continue
    bucket.set(r.case_id, [...(bucket.get(r.case_id) ?? []), v])
  }
  return new Map([...bucket].map(([k, v]) => [k, mean(v)]))
}

/** Mean over cases for each repeat index; its spread is the run-to-run noise. */
function repeatMeans(run: EvalRunExport, metric: string): number[] {
  const byRepeat = new Map<number, number[]>()
  for (const r of run.results) {
    const v = numericMetrics(r.metrics)[metric]
    if (v === undefined) continue
    byRepeat.set(r.repeat_idx, [...(byRepeat.get(r.repeat_idx) ?? []), v])
  }
  return [...byRepeat.values()].map(mean)
}

export function compareRuns(a: EvalRunExport, b: EvalRunExport): Comparison {
  const names = new Set<string>()
  for (const run of [a, b]) for (const r of run.results) Object.keys(numericMetrics(r.metrics)).forEach((k) => names.add(k))
  const casesA = new Set(a.results.map((r) => r.case_id))
  const casesB = new Set(b.results.map((r) => r.case_id))
  const paired = [...casesA].filter((c) => casesB.has(c))

  const metrics: MetricComparison[] = [...names].sort().map((metric) => {
    const ma = perCaseMeans(a, metric)
    const mb = perCaseMeans(b, metric)
    const cases: PairedCase[] = []
    for (const [caseId, va] of ma) {
      const vb = mb.get(caseId)
      if (vb === undefined) continue
      const delta = vb - va
      cases.push({ caseId, a: va, b: vb, delta, outcome: Math.abs(delta) < 1e-9 ? 'tie' : delta > 0 ? 'win' : 'loss' })
    }
    const deltas = cases.map((c) => c.delta)
    const ra = repeatMeans(a, metric)
    const rb = repeatMeans(b, metric)
    const spreadA = sampleSd(ra)
    const spreadB = sampleSd(rb)
    const meanDelta = mean(deltas)
    const noise = Math.max(Number.isNaN(spreadA) ? NaN : spreadA, Number.isNaN(spreadB) ? NaN : spreadB)
    let verdict: MetricComparison['verdict'] = 'unknown'
    if (cases.length && !Number.isNaN(noise)) {
      verdict = Math.abs(meanDelta) > noise ? (meanDelta > 0 ? 'improved' : 'regressed') : 'within-noise'
    }
    return {
      metric,
      meanA: mean([...ma.values()]),
      meanB: mean([...mb.values()]),
      spreadA,
      spreadB,
      repeatsA: ra.length,
      repeatsB: rb.length,
      meanDelta,
      deltaSe: deltas.length > 1 ? sampleSd(deltas) / Math.sqrt(deltas.length) : NaN,
      wins: cases.filter((c) => c.outcome === 'win').length,
      losses: cases.filter((c) => c.outcome === 'loss').length,
      ties: cases.filter((c) => c.outcome === 'tie').length,
      verdict,
      cases,
    }
  })

  return {
    metrics,
    onlyInA: [...casesA].filter((c) => !casesB.has(c)).sort(),
    onlyInB: [...casesB].filter((c) => !casesA.has(c)).sort(),
    pairedCases: paired.length,
    sameFingerprint: a.run.config_fingerprint === b.run.config_fingerprint,
  }
}
