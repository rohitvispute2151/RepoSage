<script setup lang="ts">
import { computed } from 'vue'
import type { ConnectionState } from '@/lib/sse'
import AppButton from './AppButton.vue'

const props = defineProps<{ state: ConnectionState }>()
defineEmits<{ retry: [] }>()

const view = computed(() => {
  const s = props.state
  switch (s.phase) {
    case 'connecting': return { tone: 'bg-surface-3 text-fg', still: false, text: 'Connecting to the live event stream…', retry: false }
    case 'open': return { tone: 'bg-success-bg text-success', still: false, text: 'Live: receiving events.', retry: false }
    case 'reconnecting': return { tone: 'bg-warning-bg text-warning', still: false, text: `Connection lost (${s.reason}). Reconnecting in ${Math.round(s.delayMs / 1000)}s, attempt ${s.attempt}. Resuming from the last event.`, retry: false }
    case 'closed': return { tone: 'bg-surface-3 text-fg', still: true, text: 'Stream finished. The task reached a final state.', retry: false }
    case 'failed': return { tone: 'bg-danger-bg text-danger', still: true, text: s.fatal ? `${s.reason}. Not retrying.` : `${s.reason}.`, retry: !s.fatal }
    default: return { tone: 'bg-surface-3 text-fg', still: true, text: 'Not connected.', retry: false }
  }
})
</script>

<template>
  <div class="inline-flex max-w-full flex-wrap items-center gap-3 rounded-full px-3.5 py-1.5 text-xs font-medium" :class="view.tone" role="status" data-testid="connection-banner" :data-phase="state.phase">
    <span aria-hidden="true" class="live-dot" :class="{ still: view.still }" />
    <span>{{ view.text }}</span>
    <AppButton v-if="view.retry" @click="$emit('retry')">Reconnect now</AppButton>
  </div>
</template>
