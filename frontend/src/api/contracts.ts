/**
 * Zod contracts for everything the OpenAPI document cannot describe:
 *  - the SSE event stream (OpenAPI has no model for text/event-stream),
 *  - `TaskResponse.result` / `.budgets`, which FastAPI exposes as untyped `dict`,
 *  - eval run exports (the backend has no eval endpoint yet, see docs/BACKEND_CONTRACT.md).
 * Request/response types for the REST endpoints come from the generated `schema.d.ts`.
 */
import { z } from 'zod'

// ---- Task status ---------------------------------------------------------------------------

export const TASK_STATUSES = [
  'queued',
  'running',
  'awaiting_approval',
  'completed',
  'failed',
  'budget_exceeded',
  'cancelled',
  'approval_timeout',
] as const
export const TaskStatusSchema = z.enum(TASK_STATUSES)
export type TaskStatus = z.infer<typeof TaskStatusSchema>

export const TERMINAL_STATUSES: readonly TaskStatus[] = ['completed', 'failed', 'budget_exceeded', 'cancelled', 'approval_timeout']

// ---- Budgets and results -------------------------------------------------------------------

export const BudgetLimitsSchema = z.object({
  max_steps: z.number().optional(),
  max_tokens: z.number().optional(),
  max_usd: z.number().optional(),
  max_seconds: z.number().optional(),
})
export type BudgetLimits = z.infer<typeof BudgetLimitsSchema>

export const BudgetUsageSchema = z.object({
  steps: z.number(),
  tokens: z.number(),
  usd: z.number(),
  seconds: z.number(),
})
export type BudgetUsage = z.infer<typeof BudgetUsageSchema>

export const CitationSchema = z.object({
  path: z.string(),
  start_line: z.number().int(),
  end_line: z.number().int(),
  symbol: z.string(),
})
export type Citation = z.infer<typeof CitationSchema>

export const VerifyResultSchema = z.looseObject({
  all_target_pass: z.boolean(),
  regressions: z.number().default(0),
  policy_ok: z.boolean(),
  failure_digest: z.string().default(''),
  // LLD §9.1 sandbox shape; the current verify node does not forward these, so they stay optional.
  tests: z
    .array(z.object({ id: z.string(), outcome: z.string(), duration_ms: z.number().optional() }))
    .optional(),
  summary: z.record(z.string(), z.number()).optional(),
  log_tail: z.string().optional(),
})
export type VerifyResult = z.infer<typeof VerifyResultSchema>

export const TaskResultSchema = z.looseObject({
  outcome: z.string(),
  answer: z.string().nullish(),
  citations: z.array(CitationSchema).default([]),
  /** Prompted for by answer.v1.md but dropped by the report node; honoured when present. */
  found: z.boolean().optional(),
  patch_diff: z.string().nullish(),
  test_summary: VerifyResultSchema.partial().nullish(),
  rationale: z.string().nullish(),
  applied: z.boolean().optional(),
  budget_report: z
    .looseObject({
      steps: z.number().optional(),
      tokens: z.number().optional(),
      usd: z.number().optional(),
      seconds: z.number().optional(),
      limits: BudgetLimitsSchema.optional(),
    })
    .default({}),
  notes: z.array(z.string()).default([]),
})
export type TaskResult = z.infer<typeof TaskResultSchema>

// ---- SSE events ----------------------------------------------------------------------------

export const EventPayloads = {
  node_started: z.looseObject({ node: z.string() }),
  node_finished: z.looseObject({ node: z.string(), passed: z.boolean().optional(), validation: z.boolean().optional() }),
  /** Documented in LLD §3 (`task_events.type`) but not emitted by the current backend. */
  tool_call: z.looseObject({
    tool: z.string(),
    status: z.enum(['allowed', 'denied', 'ok', 'error', 'timeout']),
    denial_reason: z.string().nullish(),
    args_hash: z.string().nullish(),
    duration_ms: z.number().nullish(),
    node: z.string().nullish(),
    step_id: z.number().nullish(),
  }),
  llm_call: z.looseObject({
    model: z.string(),
    node: z.string().nullish(),
    tokens_in: z.number(),
    tokens_out: z.number(),
    cost_usd: z.number(),
    latency_ms: z.number().nullish(),
  }),
  budget: BudgetUsageSchema.extend({ limits: BudgetLimitsSchema.optional() }),
  approval_requested: z.looseObject({
    patch_id: z.string().nullish(),
    diff: z.string(),
    sha256: z.string().min(1),
    test_evidence: VerifyResultSchema.partial().nullish(),
    rationale: z.string().nullish(),
  }),
  patch_applied: z.looseObject({ applied: z.boolean(), error: z.string().nullish() }),
  patch_rejected: z.looseObject({ comment: z.string().nullish() }),
  completed: z.looseObject({ status: z.string(), outcome: z.string() }),
  done: z.looseObject({ status: z.string() }),
} as const

export type EventName = keyof typeof EventPayloads
export type EventData = { [K in EventName]: z.infer<(typeof EventPayloads)[K]> }

export type KnownEntry = { [K in EventName]: { kind: 'known'; seq: number | null; name: K; data: EventData[K] } }[EventName]
export type InvalidEntry = { kind: 'invalid'; seq: number | null; name: string; reason: string }
export type UnknownEntry = { kind: 'unknown'; seq: number | null; name: string }
export type StreamEntry = KnownEntry | InvalidEntry | UnknownEntry

export function parseSseEvent(name: string, rawData: string, seq: number | null): StreamEntry {
  if (!(name in EventPayloads)) return { kind: 'unknown', seq, name }
  let json: unknown
  try {
    json = JSON.parse(rawData)
  } catch {
    return { kind: 'invalid', seq, name, reason: 'payload is not valid JSON' }
  }
  const schema = EventPayloads[name as EventName]
  const parsed = schema.safeParse(json)
  if (!parsed.success) {
    const first = parsed.error.issues[0]
    return { kind: 'invalid', seq, name, reason: `${first?.path.join('.') || 'payload'}: ${first?.message ?? 'invalid'}` }
  }
  return { kind: 'known', seq, name: name as EventName, data: parsed.data } as KnownEntry
}

// ---- Eval exports --------------------------------------------------------------------------

export const EvalRunExportSchema = z.object({
  run: z.object({
    id: z.string(),
    suite_id: z.string().optional(),
    label: z.string().nullish(),
    config_fingerprint: z.string(),
    started_at: z.string().optional(),
    finished_at: z.string().nullish(),
  }),
  results: z.array(
    z.object({
      case_id: z.string(),
      repeat_idx: z.number().int().default(0),
      task_id: z.string().nullish(),
      metrics: z.record(z.string(), z.unknown()),
    }),
  ),
})
export type EvalRunExport = z.infer<typeof EvalRunExportSchema>
