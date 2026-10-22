<script setup lang="ts">
import { computed, onBeforeUnmount, watch } from 'vue'
import { useQueryClient } from '@tanstack/vue-query'
import { useTask } from '@/composables/useTask'
import { useTrajectoryStore } from '@/stores/trajectory'
import { useHistoryStore } from '@/stores/history'
import { STATUS_META, UNKNOWN_STATUS_META } from '@/lib/statusMeta'
import StatusBadge from '@/components/StatusBadge.vue'
import ConnectionBanner from '@/components/ConnectionBanner.vue'
import ErrorState from '@/components/ErrorState.vue'
import AppButton from '@/components/AppButton.vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import AppIcon from '@/components/AppIcon.vue'
import { cancelTask } from '@/api/tasks'
import { useMutation } from '@tanstack/vue-query'
import { ref } from 'vue'

const props = defineProps<{ id: string }>()
const id = computed(() => props.id)
const store = useTrajectoryStore()
const qc = useQueryClient()
const { data: task, error, isPending, refetch } = useTask(id)

watch(id, (v) => store.start(v), { immediate: true })
const history = useHistoryStore()
watch(() => task.value, (t) => { if (t) history.addTask({ id: t.id, mode: t.mode, label: t.mode === 'qa' ? 'Question' : 'Fix' }) })
onBeforeUnmount(() => store.stop())
// Events that imply a status change (approval requested, completed, ...) make the polled status stale: pull it now.
watch(() => store.statusSignal, () => { void qc.invalidateQueries({ queryKey: ['task', id.value] }) })

const meta = computed(() => (task.value && task.value.status !== 'unknown' ? STATUS_META[task.value.status] : UNKNOWN_STATUS_META))
const confirmCancel = ref(false)
const cancel = useMutation({
  mutationFn: () => cancelTask(id.value),
  onSettled: () => { confirmCancel.value = false; void qc.invalidateQueries({ queryKey: ['task', id.value] }) },
})
const cancellable = computed(() => !!task.value && ['queued', 'running', 'awaiting_approval'].includes(task.value.status))
const showConnection = computed(() => store.connection.phase !== 'idle')
// Auth/404 on the task itself already explains why the stream is dead.
const streamIsRedundant = computed(() => !!error.value && store.connection.phase === 'failed')
const tabs = computed(() => {
  const t = [{ name: 'trajectory', label: 'Trajectory' }]
  if (!task.value || task.value.mode !== 'qa') t.push({ name: 'review', label: 'Patch review' })
  if (!task.value || task.value.mode !== 'fix') t.push({ name: 'answer', label: 'Answer' })
  return t
})
</script>

<template>
  <div class="space-y-6">
    <ErrorState v-if="error" :error="error" @retry="refetch()" />
    <p v-else-if="isPending" class="card-flat animate-pulse px-5 py-8 text-sm text-muted" role="status">Loading task…</p>
    <template v-else-if="task">
      <header class="card relative overflow-hidden p-5 sm:p-6">
        <div class="pointer-events-none absolute -right-16 -top-20 size-56 rounded-full bg-accent/10 blur-3xl" aria-hidden="true" />
        <div class="relative flex flex-wrap items-start gap-4">
          <span class="grid size-12 shrink-0 place-items-center rounded-2xl bg-accent-soft text-accent"><AppIcon :name="task.mode === 'fix' ? 'wrench' : 'chat'" :size="24" /></span>
          <div class="min-w-0 flex-1 basis-[14rem]">
            <p class="eyebrow">{{ task.mode === 'fix' ? 'Fix task' : 'Question task' }}</p>
            <h1 class="mt-1 flex flex-wrap items-baseline gap-x-3 gap-y-1 text-2xl font-semibold tracking-tight">{{ task.mode === 'qa' ? 'Question' : task.mode === 'fix' ? 'Fix' : 'Task' }} <span class="break-all font-mono text-sm font-normal text-muted">{{ task.id }}</span></h1>
            <div class="mt-3 flex flex-wrap items-center gap-3">
              <StatusBadge :status="task.status" :raw="task.rawStatus" />
              <span v-if="task.outcome" class="text-sm text-muted">Outcome: <span class="hash-chip !text-fg" data-testid="outcome">{{ task.outcome }}</span></span>
            </div>
            <p class="mt-3 max-w-3xl text-sm leading-6 text-muted" data-testid="status-summary">{{ meta.summary }}</p>
          </div>
          <AppButton v-if="cancellable" variant="danger" data-testid="cancel-task" @click="confirmCancel = true">Cancel task</AppButton>
        </div>
      </header>
      <ConfirmDialog v-model:open="confirmCancel" title="Cancel this task?" variant="danger" confirm-label="Cancel task" :busy="cancel.isPending.value" description="The agent stops and any pending patch is discarded. Nothing is applied." @confirm="cancel.mutate()">
        <p v-if="cancel.error.value" role="alert" class="rounded-xl bg-danger-bg px-3 py-2 text-sm text-danger">{{ cancel.error.value.message }}</p>
      </ConfirmDialog>
    </template>

    <div class="flex flex-wrap items-center justify-between gap-3">
      <nav aria-label="Task views" class="inline-flex gap-1 rounded-xl border border-line bg-surface-2 p-1">
        <RouterLink
          v-for="t in tabs"
          :key="t.name"
          :to="{ name: t.name, params: { id } }"
          class="rounded-lg px-4 py-1.5 text-sm font-medium text-muted transition hover:text-fg"
          active-class=""
          exact-active-class="!bg-surface !text-fg shadow-[var(--shadow)]"
        >{{ t.label }}</RouterLink>
      </nav>
      <ConnectionBanner v-if="showConnection && !streamIsRedundant" :state="store.connection" @retry="store.retry()" />
    </div>

    <RouterView />
  </div>
</template>
