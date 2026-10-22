import { api, unwrap, ApiError } from './client'
import type { components } from './schema'
import {
  BudgetLimitsSchema,
  TaskResultSchema,
  TaskStatusSchema,
  type BudgetLimits,
  type TaskResult,
  type TaskStatus,
} from './contracts'
import type { PendingPatch } from '@/stores/trajectory'

export type TaskResponse = components['schemas']['TaskResponse']
export type ApprovalBody = components['schemas']['ApprovalDecision']

/** TaskResponse with its untyped `dict` fields (status, budgets, result) validated. */
export interface TaskView {
  id: string
  snapshotId: string
  mode: 'qa' | 'fix' | 'unknown'
  status: TaskStatus | 'unknown'
  rawStatus: string
  outcome: string | null
  budgets: BudgetLimits
  result: TaskResult | null
  resultProblem: string | null
  createdAt: string
  updatedAt: string
}

export function toTaskView(t: TaskResponse): TaskView {
  const status = TaskStatusSchema.safeParse(t.status)
  const budgets = BudgetLimitsSchema.safeParse(t.budgets)
  let result: TaskResult | null = null
  let resultProblem: string | null = null
  if (t.result) {
    const r = TaskResultSchema.safeParse(t.result)
    if (r.success) result = r.data
    else resultProblem = r.error.issues[0] ? `${r.error.issues[0].path.join('.')}: ${r.error.issues[0].message}` : 'unreadable result'
  }
  return {
    id: t.id,
    snapshotId: t.snapshot_id,
    mode: t.mode === 'qa' || t.mode === 'fix' ? t.mode : 'unknown',
    status: status.success ? status.data : 'unknown',
    rawStatus: t.status,
    outcome: t.outcome ?? null,
    budgets: budgets.success ? budgets.data : {},
    result,
    resultProblem,
    createdAt: t.created_at,
    updatedAt: t.updated_at,
  }
}

export async function fetchTask(taskId: string): Promise<TaskView> {
  const data = await unwrap(api.GET('/v1/tasks/{task_id}', { params: { path: { task_id: taskId } } }))
  return toTaskView(data)
}

export type Decision =
  | { decision: 'approve'; comment?: string }
  | { decision: 'reject'; comment?: string }
  | { decision: 'edit'; editedDiff: string; comment?: string }

/**
 * The single place in the app that POSTs an approval decision. It requires a PendingPatch (which only the SSE
 * `approval_requested` event can produce) and always sends that patch's sha256, so there is no code path that
 * approves without the current hash and none that applies a patch without an approval request.
 */
export async function submitApproval(taskId: string, pending: PendingPatch, d: Decision): Promise<void> {
  if (!pending.sha256) throw new ApiError('contract', null, 'No pending patch hash; refusing to send a decision.')
  const body: ApprovalBody = {
    decision: d.decision,
    patch_sha256: pending.sha256,
    ...(d.decision === 'edit' ? { edited_diff: d.editedDiff } : {}),
    ...(d.comment ? { comment: d.comment } : {}),
  }
  await unwrap(api.POST('/v1/tasks/{task_id}/approval', { params: { path: { task_id: taskId } }, body }))
}

export type TaskCreate = components['schemas']['TaskCreate']

export const createTask = (body: TaskCreate) => unwrap(api.POST('/v1/tasks', { body }))

/** Cancels a queued, running or awaiting-approval task. Never applies anything. */
export const cancelTask = (taskId: string) => unwrap(api.POST('/v1/tasks/{task_id}/cancel', { params: { path: { task_id: taskId } } }))
