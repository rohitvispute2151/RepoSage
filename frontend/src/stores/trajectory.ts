import { defineStore } from 'pinia'
import { computed, ref, shallowRef } from 'vue'
import { parseSseEvent, type BudgetUsage, type EventData, type KnownEntry, type StreamEntry } from '@/api/contracts'
import { API_BASE } from '@/api/client'
import { runSse, type ConnectionState } from '@/lib/sse'
import { NODE_ORDER } from '@/lib/statusMeta'
import { useSessionStore } from './session'

type Known<K extends KnownEntry['name']> = Extract<KnownEntry, { name: K }>

/**
 * A patch the backend is waiting on. Only ever built from an `approval_requested` event, and the brand makes it
 * impossible to hand-craft a sha for an approval call elsewhere in the app.
 */
export type PendingPatch = Readonly<EventData['approval_requested']> & { readonly __brand: 'PendingPatch'; readonly seq: number | null }

export interface ToolCallRow {
  key: string
  seq: number | null
  tool: string
  status: EventData['tool_call']['status']
  denialReason: string | null
  durationMs: number | null
  node: string | null
}

export interface NodeVisit {
  node: string
  visit: number
  state: 'active' | 'done'
  passed: boolean | null
}

const RESOLVING = new Set(['patch_applied', 'patch_rejected', 'completed', 'done'])

export const useTrajectoryStore = defineStore('trajectory', () => {
  const taskId = ref<string | null>(null)
  const entries = shallowRef<StreamEntry[]>([])
  const lastSeq = ref(0)
  const connection = ref<ConnectionState>({ phase: 'idle' })
  const generation = ref(0)
  let controller: AbortController | null = null

  const known = computed(() => entries.value.filter((e): e is KnownEntry => e.kind === 'known'))
  const invalid = computed(() => entries.value.filter((e) => e.kind === 'invalid'))
  const unknownCount = computed(() => entries.value.filter((e) => e.kind === 'unknown').length)

  const nodeVisits = computed<NodeVisit[]>(() => {
    const out: NodeVisit[] = []
    const counts = new Map<string, number>()
    for (const e of known.value) {
      if (e.name === 'node_started') {
        const n = (counts.get(e.data.node) ?? 0) + 1
        counts.set(e.data.node, n)
        out.push({ node: e.data.node, visit: n, state: 'active', passed: null })
      } else if (e.name === 'node_finished') {
        const open = [...out].reverse().find((v) => v.node === e.data.node && v.state === 'active')
        if (open) {
          open.state = 'done'
          open.passed = e.data.passed ?? e.data.validation ?? null
        }
      }
    }
    return out
  })

  const nodeSummary = computed(() =>
    NODE_ORDER.map((node) => {
      const visits = nodeVisits.value.filter((v) => v.node === node)
      const active = visits.some((v) => v.state === 'active')
      return { node, visits: visits.length, state: active ? 'active' : visits.length ? 'done' : 'pending' } as const
    }),
  )

  const toolCalls = computed<ToolCallRow[]>(() =>
    known.value
      .filter((e): e is Known<'tool_call'> => e.name === 'tool_call')
      .map((e, i) => ({
        key: `${e.seq ?? 'x'}-${i}`,
        seq: e.seq,
        tool: e.data.tool,
        status: e.data.status,
        denialReason: e.data.denial_reason ?? null,
        durationMs: e.data.duration_ms ?? null,
        node: e.data.node ?? null,
      })),
  )

  /** Latest `budget` event, else usage derived from what the stream does show (steps only). */
  const budget = computed<{ usage: Partial<BudgetUsage>; source: 'stream' | 'derived' }>(() => {
    const events = known.value.filter((e): e is Known<'budget'> => e.name === 'budget')
    const last = events[events.length - 1]
    if (last) return { usage: { steps: last.data.steps, tokens: last.data.tokens, usd: last.data.usd, seconds: last.data.seconds }, source: 'stream' }
    const llm = known.value.filter((e): e is Known<'llm_call'> => e.name === 'llm_call')
    const usage: Partial<BudgetUsage> = { steps: nodeVisits.value.length }
    if (llm.length) {
      usage.tokens = llm.reduce((a, e) => a + e.data.tokens_in + e.data.tokens_out, 0)
      usage.usd = llm.reduce((a, e) => a + e.data.cost_usd, 0)
    }
    return { usage, source: 'derived' }
  })

  const pendingPatch = computed<PendingPatch | null>(() => {
    let pending: Known<'approval_requested'> | null = null
    for (const e of known.value) {
      if (e.name === 'approval_requested') pending = e
      else if (pending && RESOLVING.has(e.name)) pending = null
    }
    return pending ? ({ ...pending.data, seq: pending.seq } as PendingPatch) : null
  })

  /**
   * Changes whenever the stream carries something that implies a task-status change, so the view can refetch
   * immediately instead of waiting for the next poll.
   */
  const statusSignal = computed(() => {
    let n = 0
    for (const e of known.value) {
      if (e.name === 'approval_requested' || e.name === 'completed' || e.name === 'done' || e.name.startsWith('patch_')) n++
      else if (e.name === 'node_started' && n === 0) n = 0.5
    }
    return n + (known.value.some((e) => e.name === 'node_started') ? 0.5 : 0)
  })

  const finished = computed(() => known.value.some((e) => e.name === 'done' || e.name === 'completed'))

  function ingest(name: string, id: string | null, data: string) {
    const parsedId = id !== null && /^\d+$/.test(id) ? Number(id) : null
    if (parsedId !== null && parsedId <= lastSeq.value) return // replay after reconnect: already consumed
    if (parsedId !== null) lastSeq.value = parsedId
    entries.value = [...entries.value, parseSseEvent(name, data, parsedId)]
  }

  function stream() {
    controller?.abort()
    const ac = new AbortController()
    controller = ac
    const session = useSessionStore()
    const id = taskId.value
    if (!id) return
    void runSse({
      url: `${API_BASE}/v1/tasks/${encodeURIComponent(id)}/events`,
      headers: (): Record<string, string> => (session.apiKey ? { 'X-API-Key': session.apiKey } : {}),
      signal: ac.signal,
      getLastEventId: () => lastSeq.value,
      onMessage: (m) => ingest(m.event, m.id, m.data),
      onState: (s) => { if (controller === ac) connection.value = s },
    })
  }

  function start(id: string) {
    if (taskId.value === id && controller && !controller.signal.aborted) return
    stop()
    taskId.value = id
    entries.value = []
    lastSeq.value = 0
    generation.value++
    stream()
  }

  function stop() {
    controller?.abort()
    controller = null
    connection.value = { phase: 'idle' }
  }

  /** Manual retry after the client gave up; resumes from Last-Event-ID. */
  function retry() {
    stream()
  }

  /** Drop everything and replay the whole stream, so a changed patch is picked up. */
  function refetch() {
    const id = taskId.value
    if (!id) return
    stop()
    entries.value = []
    lastSeq.value = 0
    generation.value++
    stream()
  }

  return { taskId, entries, lastSeq, connection, generation, invalid, unknownCount, nodeVisits, nodeSummary, toolCalls, budget, pendingPatch, finished, statusSignal, start, stop, retry, refetch }
})
