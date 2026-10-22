<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useTask } from '@/composables/useTask'
import { useTrajectoryStore } from '@/stores/trajectory'
import ApprovalPanel from '@/components/ApprovalPanel.vue'
import DiffViewer from '@/components/DiffViewer.vue'
import TestEvidence from '@/components/TestEvidence.vue'
import EmptyState from '@/components/EmptyState.vue'

const route = useRoute()
const id = computed(() => String(route.params.id))
const store = useTrajectoryStore()
const { data: task } = useTask(id)

const awaiting = computed(() => task.value?.status === 'awaiting_approval')
const blockedReason = computed(() =>
  awaiting.value ? '' : `This task is ${task.value?.status.replaceAll('_', ' ') ?? 'not loaded'}, not awaiting approval, so decisions are disabled.`,
)
const result = computed(() => task.value?.result ?? null)
const streamLoading = computed(() => ['connecting', 'reconnecting'].includes(store.connection.phase))
</script>

<template>
  <div>
    <EmptyState v-if="task?.mode === 'qa'" title="No patch for a question task">Question tasks produce answers, not patches. Open the Answer tab.</EmptyState>

    <ApprovalPanel
      v-else-if="store.pendingPatch"
      :key="store.pendingPatch.sha256 + store.generation"
      :task-id="id"
      :pending="store.pendingPatch"
      :can-decide="awaiting"
      :blocked-reason="blockedReason"
      @refetch="store.refetch()"
    />

    <div v-else-if="result?.patch_diff" class="space-y-5" data-testid="final-patch">
      <div class="rounded-2xl border border-line-strong bg-surface-3 px-4 py-3 text-sm">
        <template v-if="task?.status === 'approval_timeout'">The approval window closed. This patch was discarded and <strong>not</strong> applied.</template>
        <template v-else-if="task?.status === 'cancelled'">The task was cancelled. This patch was <strong>not</strong> applied.</template>
        <template v-else-if="result.applied">This patch was approved and applied.</template>
        <template v-else>No decision is pending. This patch was <strong>not</strong> applied (outcome: {{ task?.outcome ?? result.outcome }}).</template>
      </div>
      <h2 class="sr-only">Patch and test evidence</h2>
      <DiffViewer :diff="result.patch_diff" />
      <TestEvidence :evidence="result.test_summary" />
    </div>

    <EmptyState v-else-if="!task || ['queued', 'running'].includes(task.status) || streamLoading" title="No patch to review yet">
      The agent has not produced a verified patch. This page updates when it does.
    </EmptyState>
    <EmptyState v-else title="This task finished without a patch">
      Outcome: {{ task.outcome ?? 'unknown' }}. Check the trajectory for where the agent stopped.
    </EmptyState>
  </div>
</template>
