import type { TaskStatus } from '@/api/contracts'

export type Tone = 'neutral' | 'info' | 'success' | 'warning' | 'danger'

export interface StatusMeta {
  label: string
  tone: Tone
  terminal: boolean
  /** Shown in the status panel: what is happening and what the reader can do. */
  summary: string
}

export const STATUS_META: Record<TaskStatus, StatusMeta> = {
  queued: { label: 'Queued', tone: 'neutral', terminal: false, summary: 'Waiting for a worker to pick this task up. If it stays here, check that the Celery worker is running.' },
  running: { label: 'Running', tone: 'info', terminal: false, summary: 'The agent is working. Progress streams in below.' },
  awaiting_approval: { label: 'Awaiting approval', tone: 'warning', terminal: false, summary: 'A verified patch is waiting for a human decision. Nothing is applied until you approve.' },
  completed: { label: 'Completed', tone: 'success', terminal: true, summary: 'The task finished. See the outcome and result.' },
  failed: { label: 'Failed', tone: 'danger', terminal: true, summary: 'The task failed. Check the event log for the last step reached.' },
  budget_exceeded: { label: 'Budget exceeded', tone: 'warning', terminal: true, summary: 'A step, token, cost or time limit was hit. A partial report is shown if the agent produced one.' },
  cancelled: { label: 'Cancelled', tone: 'neutral', terminal: true, summary: 'The task was cancelled. Any pending patch was discarded.' },
  approval_timeout: { label: 'Approval timed out', tone: 'danger', terminal: true, summary: 'No decision arrived before the approval window closed. The patch was discarded and nothing was applied.' },
}

export const UNKNOWN_STATUS_META: StatusMeta = {
  label: 'Unknown status',
  tone: 'danger',
  terminal: false,
  summary: 'The server reported a status this console does not know. The UI and backend may be out of sync.',
}

export const NODE_ORDER = ['plan', 'retrieve', 'explore', 'patch', 'verify', 'approval', 'report'] as const
export type NodeName = (typeof NODE_ORDER)[number]
