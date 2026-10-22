import { describe, expect, it } from 'vitest'
import { parseSseEvent, TASK_STATUSES, TaskResultSchema } from '@/api/contracts'
import { STATUS_META } from '@/lib/statusMeta'

describe('SSE event validation', () => {
  it('accepts a well-formed approval_requested', () => {
    const e = parseSseEvent('approval_requested', JSON.stringify({ patch_id: 'p', diff: 'd', sha256: 'abc', test_evidence: { all_target_pass: true, regressions: 0, policy_ok: true, failure_digest: '' }, rationale: 'r' }), 5)
    expect(e).toMatchObject({ kind: 'known', name: 'approval_requested', seq: 5 })
  })

  it('flags a payload missing the sha256 as invalid instead of dropping it', () => {
    const e = parseSseEvent('approval_requested', JSON.stringify({ diff: 'd' }), 5)
    expect(e).toMatchObject({ kind: 'invalid', name: 'approval_requested' })
  })

  it('flags non-JSON and wrong-type payloads', () => {
    expect(parseSseEvent('node_started', '{oops', 1).kind).toBe('invalid')
    expect(parseSseEvent('node_started', '{"node": 3}', 1).kind).toBe('invalid')
    expect(parseSseEvent('tool_call', '{"tool":"grep","status":"weird"}', 1).kind).toBe('invalid')
  })

  it('keeps unknown event types visible but non-fatal', () => {
    expect(parseSseEvent('future_event', '{}', 9)).toEqual({ kind: 'unknown', seq: 9, name: 'future_event' })
  })

  it('tolerates extra fields', () => {
    expect(parseSseEvent('node_finished', '{"node":"verify","passed":true,"extra":1}', 2).kind).toBe('known')
  })
})

describe('task status', () => {
  it('has display metadata for all 8 backend statuses', () => {
    expect(TASK_STATUSES).toHaveLength(8)
    for (const s of TASK_STATUSES) expect(STATUS_META[s].label).toBeTruthy()
  })
  it('marks exactly the backend terminal set as terminal', () => {
    const terminal = TASK_STATUSES.filter((s) => STATUS_META[s].terminal).sort()
    expect(terminal).toEqual(['approval_timeout', 'budget_exceeded', 'cancelled', 'completed', 'failed'])
  })
})

describe('task result', () => {
  it('defaults missing arrays', () => {
    const r = TaskResultSchema.parse({ outcome: 'answered', answer: 'x' })
    expect(r.citations).toEqual([])
    expect(r.notes).toEqual([])
  })
  it('rejects a result with no outcome', () => {
    expect(TaskResultSchema.safeParse({ answer: 'x' }).success).toBe(false)
  })
})
