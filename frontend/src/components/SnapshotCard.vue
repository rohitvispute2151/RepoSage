<script setup lang="ts">
import { computed } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import { fetchSnapshot, isSnapshotFinal } from '@/api/repos'
import AppIcon from './AppIcon.vue'
import ErrorState from './ErrorState.vue'

const props = defineProps<{ id: string; name?: string; source?: string }>()
const emit = defineEmits<{ select: [id: string] }>()
const { data, error, refetch } = useQuery({
  queryKey: computed(() => ['snapshot', props.id]),
  queryFn: () => fetchSnapshot(props.id),
  refetchInterval: (q) => (q.state.data && isSnapshotFinal(q.state.data.status) ? false : 2000),
})
const tone = computed(() => ({ ready: 'bg-success-bg text-success', failed: 'bg-danger-bg text-danger', ingesting: 'bg-info-bg text-info', queued: 'bg-surface-3 text-fg' })[data.value?.status ?? 'queued'] ?? 'bg-warning-bg text-warning')
const working = computed(() => data.value?.status === 'ingesting' || data.value?.status === 'queued')
const modules = computed(() => Object.keys(data.value?.repo_map ?? {}))
</script>

<template>
  <li class="card p-5" :data-testid="`snapshot-${id}`" :data-status="data?.status">
    <ErrorState v-if="error" :error="error" @retry="refetch()" />
    <template v-else>
      <div class="flex flex-wrap items-center gap-3">
        <span class="grid size-9 place-items-center rounded-xl bg-surface-3 text-accent"><AppIcon name="repo" :size="18" /></span>
        <p class="font-semibold tracking-tight">{{ name ?? 'Snapshot' }}</p>
        <span v-if="data" class="chip" :class="tone"><span aria-hidden="true" class="live-dot" :class="{ still: !working }" />{{ data.status }}</span>
        <span v-else class="text-sm text-muted" role="status">Loading…</span>
        <button v-if="data?.status === 'ready'" type="button" class="link ml-auto inline-flex items-center gap-1.5 text-sm font-medium" @click="emit('select', id)">Start a task on this snapshot<AppIcon name="arrow" :size="15" /></button>
      </div>
      <p class="mt-3 flex flex-wrap items-center gap-2">
        <span class="hash-chip"><AppIcon name="hash" :size="12" /><span class="break-all">{{ id }}</span></span>
        <span v-if="data" class="hash-chip"><AppIcon name="commit" :size="12" />commit {{ data.commit_sha }}</span>
        <span v-if="source" class="hash-chip" data-testid="snapshot-source"><AppIcon name="repo" :size="12" /><span class="break-all">{{ source }}</span></span>
      </p>
      <div v-if="working" class="mt-4 h-1 overflow-hidden rounded-full bg-surface-3" aria-hidden="true"><div class="h-full w-1/3 animate-[slide_1.4s_ease-in-out_infinite] rounded-full bg-accent" /></div>
      <p v-if="working" class="mt-2 text-sm text-muted" role="status">Indexing the repository. Tasks need a ready snapshot to give good results.</p>
      <p v-if="data?.status === 'failed'" role="alert" class="mt-3 break-words text-sm text-danger">Indexing failed: {{ data.error ?? 'no error recorded' }}</p>
      <p v-if="data?.status === 'ready' && !modules.length" class="mt-3 text-sm text-muted">Ready, but the repo map is empty (no Python symbols found).</p>
      <details v-else-if="modules.length" class="mt-3 text-sm">
        <summary class="cursor-pointer text-muted hover:text-fg">Repo map ({{ modules.length }} modules)</summary>
        <ul class="scroll-thin mt-2 max-h-40 overflow-auto rounded-xl bg-surface-2 p-3 font-mono text-xs"><li v-for="m in modules" :key="m" class="break-all">{{ m }}</li></ul>
      </details>
    </template>
  </li>
</template>

<style>
@keyframes slide { 0% { transform: translateX(-110%); } 100% { transform: translateX(320%); } }
</style>
