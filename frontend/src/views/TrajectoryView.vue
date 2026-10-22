<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useTask } from '@/composables/useTask'
import { useTrajectoryStore } from '@/stores/trajectory'
import BudgetPanel from '@/components/BudgetPanel.vue'
import NodeStepper from '@/components/NodeStepper.vue'
import ToolCallList from '@/components/ToolCallList.vue'
import EmptyState from '@/components/EmptyState.vue'
import AppButton from '@/components/AppButton.vue'
import AppIcon from '@/components/AppIcon.vue'

const route = useRoute()
const id = computed(() => String(route.params.id))
const store = useTrajectoryStore()
const { data: task } = useTask(id)

const limits = computed(() => ({ ...task.value?.result?.budget_report?.limits, ...task.value?.budgets }))
const finalUsage = computed(() => {
  const b = task.value?.result?.budget_report
  if (!b || b.steps === undefined || b.tokens === undefined || b.usd === undefined || b.seconds === undefined) return null
  return { steps: b.steps, tokens: b.tokens, usd: b.usd, seconds: b.seconds }
})
const usage = computed(() => finalUsage.value ?? store.budget.usage)
const source = computed(() => (finalUsage.value ? 'stream' : store.budget.source))
const running = computed(() => task.value?.status === 'running' || task.value?.status === 'awaiting_approval')

const log = computed(() => store.entries.map((e, i) => ({ e, i })).reverse())
const tint = (e: (typeof store.entries)[number]) => {
  if (e.kind !== 'known') return e.kind === 'invalid' ? 'text-danger' : 'text-muted'
  switch (e.name) {
    case 'tool_call': return e.data.status === 'denied' ? 'text-danger' : e.data.status === 'ok' ? 'text-fg' : 'text-warning'
    case 'approval_requested': return 'text-warning font-semibold'
    case 'patch_applied': case 'completed': return 'text-success font-semibold'
    case 'patch_rejected': return 'text-danger'
    case 'node_started': case 'node_finished': case 'budget': return 'text-muted'
    default: return 'text-fg'
  }
}
const describe = (e: (typeof store.entries)[number]) => {
  if (e.kind === 'invalid') return `${e.name}: malformed event (${e.reason})`
  if (e.kind === 'unknown') return `${e.name}: unrecognised event type`
  switch (e.name) {
    case 'node_started': return `Started ${e.data.node}`
    case 'node_finished': return `Finished ${e.data.node}`
    case 'tool_call': return `Tool ${e.data.tool}: ${e.data.status}${e.data.denial_reason ? ` (${e.data.denial_reason})` : ''}`
    case 'llm_call': return `LLM ${e.data.model}: ${e.data.tokens_in + e.data.tokens_out} tokens`
    case 'budget': return 'Budget update'
    case 'approval_requested': return 'Patch ready: approval requested'
    case 'patch_applied': return e.data.applied ? 'Patch applied' : `Patch apply failed: ${e.data.error ?? 'unknown error'}`
    case 'patch_rejected': return 'Patch rejected'
    case 'completed': return `Completed: ${e.data.status} / ${e.data.outcome}`
    case 'done': return `Stream done (${e.data.status})`
  }
}
</script>

<template>
  <div class="space-y-6">
    <div v-if="task?.status === 'awaiting_approval'" class="flex flex-wrap items-center gap-4 rounded-2xl border border-warning/40 bg-warning-bg p-4 text-warning" role="status">
      <span class="grid size-10 place-items-center rounded-xl bg-warning/15"><AppIcon name="shield" :size="20" /></span>
      <span class="flex-1 font-medium">A patch is waiting for your decision.</span>
      <RouterLink :to="{ name: 'review', params: { id } }"><AppButton variant="primary">Review patch<AppIcon name="arrow" :size="15" /></AppButton></RouterLink>
    </div>
    <div v-if="task?.status === 'completed' && task.mode === 'qa'" class="flex items-center gap-3 rounded-2xl border border-success/30 bg-success-bg p-4 text-success" role="status">
      <AppIcon name="check" :size="20" />
      <span>The answer is ready. <RouterLink :to="{ name: 'answer', params: { id } }" class="font-semibold underline underline-offset-4">Read it</RouterLink>.</span>
    </div>

    <NodeStepper :nodes="store.nodeSummary" />
    <BudgetPanel :limits="limits" :usage="usage" :source="source" :started-at="task?.createdAt" :ticking="running" />

    <ToolCallList :calls="store.toolCalls" />

    <section aria-labelledby="log-h" class="card overflow-hidden">
      <div class="flex items-center gap-3 border-b border-line bg-surface-2/60 px-5 py-3">
        <AppIcon name="terminal" :size="16" class="text-muted" />
        <h2 id="log-h" class="text-sm font-semibold">Event log <span class="font-normal text-muted">({{ store.entries.length }} events<template v-if="store.invalid.length">, {{ store.invalid.length }} malformed</template><template v-if="store.unknownCount">, {{ store.unknownCount }} unrecognised</template>)</span></h2>
      </div>
      <div class="p-5">
        <EmptyState v-if="!store.entries.length" title="No events yet">
          <template v-if="task?.status === 'queued'">The task is queued. Events start once a worker picks it up.</template>
          <template v-else>Waiting for the first event from the stream.</template>
        </EmptyState>
        <ol v-else class="scroll-thin max-h-96 space-y-0.5 overflow-auto font-mono text-xs leading-6" data-testid="event-log">
          <li v-for="x in log" :key="x.i" class="flex gap-4 rounded px-2 hover:bg-surface-2" :class="tint(x.e)">
            <span class="w-8 shrink-0 text-right tabular-nums text-muted">{{ x.e.seq ?? '' }}</span>
            <span class="break-words">{{ describe(x.e) }}</span>
          </li>
        </ol>
      </div>
    </section>
  </div>
</template>
