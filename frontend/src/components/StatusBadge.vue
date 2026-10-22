<script setup lang="ts">
import { computed } from 'vue'
import type { TaskStatus } from '@/api/contracts'
import { STATUS_META, UNKNOWN_STATUS_META, type Tone } from '@/lib/statusMeta'

const props = defineProps<{ status: TaskStatus | 'unknown'; raw?: string }>()
const meta = computed(() => (props.status === 'unknown' ? UNKNOWN_STATUS_META : STATUS_META[props.status]))
const toneClass: Record<Tone, string> = {
  neutral: 'bg-surface-3 text-fg ring-line-strong',
  info: 'bg-info-bg text-info ring-info/30',
  success: 'bg-success-bg text-success ring-success/30',
  warning: 'bg-warning-bg text-warning ring-warning/35',
  danger: 'bg-danger-bg text-danger ring-danger/30',
}
// Only states that are in flight pulse; terminal states stay still.
const pulsing = computed(() => ['running', 'awaiting_approval', 'queued'].includes(props.status))
</script>

<template>
  <span class="chip ring-1 ring-inset" :class="toneClass[meta.tone]" :data-status="status">
    <span aria-hidden="true" class="live-dot" :class="{ still: !pulsing }" />
    {{ meta.label }}<template v-if="status === 'unknown' && raw"> ({{ raw }})</template>
  </span>
</template>
