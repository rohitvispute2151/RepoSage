<script setup lang="ts">
import { computed } from 'vue'
import { ApiError } from '@/api/errors'
import AppButton from './AppButton.vue'
import AppIcon from './AppIcon.vue'

const props = defineProps<{ error: unknown }>()
defineEmits<{ retry: [] }>()

const info = computed(() => {
  const e = props.error
  if (e instanceof ApiError) {
    switch (e.kind) {
      case 'auth': return { title: 'The API key was rejected', hint: 'Set a valid X-API-Key on the home page, then retry.', retry: false }
      case 'not_found': return { title: 'Not found', hint: 'Check the id. The task or run may not exist on this server.', retry: false }
      case 'network': return { title: 'Cannot reach the RepoSage API', hint: 'The server is offline or the network dropped. Check that the API is running.', retry: true }
      case 'server': return { title: 'The server hit an infrastructure error', hint: 'This is not a problem with your request. Retrying usually helps.', retry: true }
      case 'contract': return { title: 'Unexpected response shape', hint: 'The backend and this console disagree about a payload.', retry: true }
      default: return { title: 'Request failed', hint: '', retry: true }
    }
  }
  return { title: 'Something went wrong', hint: '', retry: true }
})
const detail = computed(() => (props.error instanceof Error ? props.error.message : String(props.error)))
</script>

<template>
  <div role="alert" class="flex gap-3 rounded-2xl border border-danger/30 bg-danger-bg p-4 text-danger" data-testid="error-state">
    <AppIcon name="alert" :size="20" class="mt-0.5" />
    <div class="min-w-0">
      <p class="font-semibold">{{ info.title }}</p>
      <p v-if="info.hint" class="mt-1 text-sm">{{ info.hint }}</p>
      <p class="mt-2 break-words font-mono text-xs opacity-90">{{ detail }}</p>
      <AppButton v-if="info.retry" class="mt-3" @click="$emit('retry')">Retry</AppButton>
    </div>
  </div>
</template>
