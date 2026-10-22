<script setup lang="ts">
import { computed } from 'vue'
import type { VerifyResult } from '@/api/contracts'
import AppIcon from './AppIcon.vue'
import EmptyState from './EmptyState.vue'

const props = defineProps<{ evidence: Partial<VerifyResult> | null | undefined }>()
const ev = computed(() => props.evidence ?? null)
const checks = computed(() => {
  const e = ev.value
  if (!e) return []
  return [
    { label: 'Target tests', ok: e.all_target_pass, text: e.all_target_pass ? 'Pass on the patched copy' : 'Still failing' },
    { label: 'Regressions', ok: e.regressions === undefined ? undefined : e.regressions === 0, text: e.regressions === undefined ? 'Not reported' : e.regressions === 0 ? 'None found' : `${e.regressions} regression(s)` },
    { label: 'Patch policy', ok: e.policy_ok, text: e.policy_ok ? 'Validator passed (no test edits, size limits)' : 'Validator failed' },
  ]
})
</script>

<template>
  <EmptyState v-if="!ev" title="No sandbox evidence attached">The approval request did not include test results. Do not approve a patch you cannot verify.</EmptyState>
  <div v-else class="space-y-5" data-testid="test-evidence">
    <ul class="grid gap-3 sm:grid-cols-3">
      <li v-for="c in checks" :key="c.label" class="card-flat flex gap-3 p-4" :data-ok="String(c.ok)">
        <span
          class="grid size-8 shrink-0 place-items-center rounded-lg"
          :class="c.ok === true ? 'bg-success-bg text-success' : c.ok === false ? 'bg-danger-bg text-danger' : 'bg-surface-3 text-muted'"
        >
          <AppIcon :name="c.ok === true ? 'check' : c.ok === false ? 'x' : 'alert'" :size="16" />
        </span>
        <div class="min-w-0">
          <p class="eyebrow">{{ c.label }}</p>
          <p class="mt-1 text-sm font-medium leading-5" :class="c.ok === true ? 'text-success' : c.ok === false ? 'text-danger' : 'text-muted'">{{ c.text }}</p>
        </div>
      </li>
    </ul>
    <div v-if="ev.tests?.length" class="card-flat scroll-thin overflow-x-auto">
      <table class="w-full text-left text-sm">
        <caption class="sr-only">Per-test results</caption>
        <thead class="eyebrow"><tr><th scope="col" class="px-4 py-2.5 font-semibold">Test</th><th scope="col" class="font-semibold">Outcome</th><th scope="col" class="pr-4 text-right font-semibold">Duration (ms)</th></tr></thead>
        <tbody>
          <tr v-for="t in ev.tests" :key="t.id" class="border-t border-line"><td class="break-all px-4 py-2 font-mono text-xs">{{ t.id }}</td><td>{{ t.outcome }}</td><td class="pr-4 text-right tabular-nums text-muted">{{ t.duration_ms ?? '–' }}</td></tr>
        </tbody>
      </table>
    </div>
    <p v-else class="text-sm text-muted">Per-test results were not included by the backend (it forwards only pass/fail, regressions and policy).</p>
    <div v-if="ev.failure_digest">
      <h3 class="eyebrow">Failure digest</h3>
      <pre class="scroll-thin mt-2 max-h-64 overflow-auto whitespace-pre-wrap rounded-xl border border-line bg-surface-2 p-4 font-mono text-xs leading-5">{{ ev.failure_digest }}</pre>
    </div>
    <div v-if="ev.log_tail">
      <h3 class="eyebrow">Log tail</h3>
      <pre class="scroll-thin mt-2 max-h-64 overflow-auto whitespace-pre-wrap rounded-xl border border-line bg-surface-2 p-4 font-mono text-xs leading-5">{{ ev.log_tail }}</pre>
    </div>
  </div>
</template>
