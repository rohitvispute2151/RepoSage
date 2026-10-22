<script setup lang="ts">
import { computed, ref } from 'vue'
import type { ToolCallRow } from '@/stores/trajectory'
import EmptyState from './EmptyState.vue'

const props = defineProps<{ calls: ToolCallRow[] }>()
const deniedOnly = ref(false)
const denied = computed(() => props.calls.filter((c) => c.status === 'denied').length)
const shown = computed(() => (deniedOnly.value ? props.calls.filter((c) => c.status === 'denied') : props.calls))
const tone = (s: ToolCallRow['status']) =>
  s === 'denied' ? 'bg-danger-bg text-danger' : s === 'error' || s === 'timeout' ? 'bg-warning-bg text-warning' : s === 'ok' ? 'bg-success-bg text-success' : 'bg-surface-3 text-fg'
</script>

<template>
  <section aria-labelledby="tools-h" class="card p-5">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <h2 id="tools-h" class="text-sm font-semibold">Tool calls <span class="font-normal text-muted">({{ calls.length }}, {{ denied }} denied)</span></h2>
      <label class="flex cursor-pointer items-center gap-2 rounded-full border border-line px-3 py-1 text-xs text-muted hover:border-line-strong hover:text-fg">
        <input v-model="deniedOnly" type="checkbox" class="size-3.5 accent-[var(--accent)]" />
        Denied only
      </label>
    </div>
    <EmptyState v-if="!calls.length" title="No tool calls reported" class="mt-4">
      Tool calls appear here as the agent makes them, including ones the policy layer denied.
    </EmptyState>
    <EmptyState v-else-if="!shown.length" title="No denied calls" class="mt-4" />
    <div v-else class="scroll-thin mt-4 overflow-x-auto">
      <table class="w-full text-left text-sm" data-testid="tool-table">
        <caption class="sr-only">Tool calls made by the agent</caption>
        <thead class="eyebrow">
          <tr><th scope="col" class="py-2 pr-3 font-semibold">#</th><th scope="col" class="pr-3 font-semibold">Tool</th><th scope="col" class="pr-3 font-semibold">Node</th><th scope="col" class="pr-3 font-semibold">Result</th><th scope="col" class="pr-3 font-semibold">Duration</th><th scope="col" class="font-semibold">Reason</th></tr>
        </thead>
        <tbody>
          <tr v-for="c in shown" :key="c.key" class="border-t border-line transition-colors hover:bg-surface-2/60" :class="c.status === 'denied' ? 'bg-danger-bg/40' : ''" :data-status="c.status">
            <td class="py-2 pr-3 tabular-nums text-muted">{{ c.seq ?? '–' }}</td>
            <td class="pr-3 font-mono text-[0.8rem]">{{ c.tool }}</td>
            <td class="pr-3 text-muted">{{ c.node ?? '–' }}</td>
            <td class="pr-3"><span class="chip !px-2 !py-0.5 !text-[0.7rem]" :class="tone(c.status)">{{ c.status }}</span></td>
            <td class="pr-3 tabular-nums text-muted">{{ c.durationMs === null ? '–' : `${c.durationMs} ms` }}</td>
            <td class="break-words font-mono text-xs text-danger">{{ c.denialReason ?? '' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
