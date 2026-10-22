<script setup lang="ts">
import { computed, reactive, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { EvalRunExport } from '@/api/contracts'
import { fetchEvalRun, parseEvalRun } from '@/api/evals'
import { compareRuns, type MetricComparison } from '@/lib/stats'
import AppButton from '@/components/AppButton.vue'
import AppIcon from '@/components/AppIcon.vue'
import EmptyState from '@/components/EmptyState.vue'
import ErrorState from '@/components/ErrorState.vue'

type Side = 'a' | 'b'
interface Slot { id: string; run: EvalRunExport | null; error: unknown; loading: boolean }
const slots = reactive<Record<Side, Slot>>({ a: { id: '', run: null, error: null, loading: false }, b: { id: '', run: null, error: null, loading: false } })
const route = useRoute()
const router = useRouter()
const names: Record<Side, string> = { a: 'Run A (baseline)', b: 'Run B (candidate)' }

async function load(side: Side) {
  const s = slots[side]
  if (!s.id.trim()) return
  s.loading = true
  s.error = null
  try {
    s.run = await fetchEvalRun(s.id.trim())
    void router.replace({ query: { ...route.query, [side]: s.id.trim() } })
  } catch (e) {
    s.run = null
    s.error = e
  } finally {
    s.loading = false
  }
}

async function loadFile(side: Side, ev: Event) {
  const file = (ev.target as HTMLInputElement).files?.[0]
  if (!file) return
  const s = slots[side]
  s.error = null
  try {
    s.run = parseEvalRun(JSON.parse(await file.text()))
    s.id = s.run.run.id
  } catch (e) {
    s.run = null
    s.error = e
  }
}

// Deep links (?a=&b=) load on arrival and whenever the query changes.
watch(
  () => [route.query.a, route.query.b] as const,
  (q) => {
    ;(['a', 'b'] as const).forEach((side, i) => {
      const v = q[i]
      if (typeof v === 'string' && v && v !== slots[side].run?.run.id && v !== slots[side].id) {
        slots[side].id = v
        void load(side)
      } else if (typeof v === 'string' && v && !slots[side].run && !slots[side].loading && !slots[side].error) void load(side)
    })
  },
  { immediate: true },
)

const comparison = computed(() => (slots.a.run && slots.b.run ? compareRuns(slots.a.run, slots.b.run) : null))
const fmt = (n: number, d = 3) => (Number.isNaN(n) ? 'n/a' : n.toFixed(d))
const signed = (n: number) => (Number.isNaN(n) ? 'n/a' : `${n > 0 ? '+' : ''}${n.toFixed(3)}`)
const verdictText: Record<MetricComparison['verdict'], string> = {
  improved: 'Improved: beats run-to-run spread',
  regressed: 'Regressed: beyond run-to-run spread',
  'within-noise': 'Within noise',
  unknown: 'Unknown: needs 2+ repeats per run',
}
const verdictTone: Record<MetricComparison['verdict'], string> = {
  improved: 'bg-success-bg text-success', regressed: 'bg-danger-bg text-danger', 'within-noise': 'bg-surface-3 text-muted', unknown: 'bg-surface-3 text-muted',
}
const verdictIcon = { improved: 'check', regressed: 'x', 'within-noise': 'activity', unknown: 'alert' } as const
const tally = computed(() => {
  const t = { improved: 0, regressed: 0, 'within-noise': 0, unknown: 0 }
  for (const m of comparison.value?.metrics ?? []) t[m.verdict]++
  return t
})
const bar = (d: number) => `${Math.min(100, Math.abs(d) * 100)}%`
</script>

<template>
  <div class="space-y-8">
    <header>
      <p class="eyebrow">Evaluation</p>
      <h1 class="mt-2 text-3xl font-semibold tracking-tight">Eval compare</h1>
      <p class="mt-2 max-w-2xl text-sm leading-6 text-muted">Single averages hide whether a change is real. Load two runs to see paired per-case deltas against run-to-run spread.</p>
    </header>

    <div class="grid gap-4 md:grid-cols-2">
      <section v-for="side in (['a', 'b'] as const)" :key="side" class="card space-y-4 p-5" :aria-labelledby="`slot-${side}`">
        <h2 :id="`slot-${side}`" class="flex items-center gap-2 text-sm font-semibold"><span class="grid size-6 place-items-center rounded-md text-xs font-bold" :class="side === 'a' ? 'bg-surface-3 text-fg' : 'bg-accent-soft text-accent'" aria-hidden="true">{{ side.toUpperCase() }}</span>{{ names[side] }}</h2>
        <form class="flex gap-2" @submit.prevent="load(side)">
          <label :for="`run-${side}`" class="sr-only">{{ names[side] }} id</label>
          <input :id="`run-${side}`" v-model="slots[side].id" type="text" placeholder="Eval run id" spellcheck="false" class="field min-w-0 flex-1 font-mono !text-[0.8rem]" />
          <AppButton type="submit" :busy="slots[side].loading">Load</AppButton>
        </form>
        <div>
          <label :for="`file-${side}`" class="block text-xs text-muted">or load an exported run JSON</label>
          <input :id="`file-${side}`" type="file" accept="application/json,.json" class="mt-1.5 w-full text-sm text-muted file:mr-3 file:cursor-pointer file:rounded-lg file:border file:border-line-strong file:bg-surface-2 file:px-3 file:py-1.5 file:text-sm file:text-fg hover:file:bg-surface-3" @change="loadFile(side, $event)" />
        </div>
        <ErrorState v-if="slots[side].error" :error="slots[side].error" @retry="load(side)" />
        <dl v-else-if="slots[side].run" class="rounded-xl bg-surface-2 p-3 text-sm" :data-testid="`run-${side}-meta`">
          <dt class="sr-only">Label</dt><dd class="font-semibold">{{ slots[side].run!.run.label ?? '(unlabelled)' }}</dd>
          <dd class="mt-1 break-all font-mono text-xs text-muted">config {{ slots[side].run!.run.config_fingerprint }}</dd>
          <dd class="mt-0.5 text-xs text-muted">{{ new Set(slots[side].run!.results.map((r) => r.case_id)).size }} cases, {{ new Set(slots[side].run!.results.map((r) => r.repeat_idx)).size }} repeat(s)</dd>
        </dl>
      </section>
    </div>

    <EmptyState v-if="!comparison" title="Load two runs to compare">Each run needs per-case results. Single averages hide whether a change is real, so this view shows paired per-case deltas and run-to-run spread.</EmptyState>

    <template v-else>
      <p v-if="comparison.sameFingerprint" role="status" class="rounded-2xl border border-warning/40 bg-warning-bg px-4 py-3 text-sm text-warning">Both runs have the same config fingerprint, so any difference is pure run-to-run noise.</p>
      <p v-if="comparison.pairedCases === 0" role="alert" class="rounded-2xl border border-danger/30 bg-danger-bg px-4 py-3 text-sm text-danger">The runs share no cases, so nothing can be paired.</p>
      <p v-if="comparison.onlyInA.length || comparison.onlyInB.length" role="status" class="rounded-2xl bg-surface-3 px-4 py-3 text-sm" data-testid="unpaired">
        Unpaired cases are excluded: {{ comparison.onlyInA.length }} only in A, {{ comparison.onlyInB.length }} only in B.
      </p>

      <ul class="grid grid-cols-2 gap-3 sm:grid-cols-4" aria-label="Verdict tally">
        <li v-for="k in (['improved', 'regressed', 'within-noise', 'unknown'] as const)" :key="k" class="card-flat flex items-center gap-3 p-4">
          <span class="grid size-9 place-items-center rounded-xl" :class="verdictTone[k]"><AppIcon :name="verdictIcon[k]" :size="17" /></span>
          <span><span class="block text-2xl font-semibold leading-none tabular-nums">{{ tally[k] }}</span><span class="mt-1 block text-xs capitalize text-muted">{{ k.replace('-', ' ') }}</span></span>
        </li>
      </ul>

      <section aria-labelledby="summary-h" class="card scroll-thin overflow-x-auto">
        <h2 id="summary-h" class="sr-only">Metric summary</h2>
        <table class="w-full text-left text-sm" data-testid="metric-table">
          <caption class="sr-only">Per-metric comparison of run A and run B over {{ comparison.pairedCases }} paired cases</caption>
          <thead class="eyebrow bg-surface-2/60">
            <tr>
              <th scope="col" class="px-4 py-3 font-semibold">Metric</th>
              <th scope="col" class="px-3 font-semibold">A mean ± spread</th>
              <th scope="col" class="px-3 font-semibold">B mean ± spread</th>
              <th scope="col" class="px-3 font-semibold">Paired Δ (B − A) ± SE</th>
              <th scope="col" class="px-3 font-semibold">Win / loss / tie</th>
              <th scope="col" class="px-3 font-semibold">Verdict</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="m in comparison.metrics" :key="m.metric" class="border-t border-line" :data-metric="m.metric" :data-verdict="m.verdict">
              <th scope="row" class="px-4 py-3.5 font-mono text-[0.82rem] font-medium">{{ m.metric }}</th>
              <td class="px-3 tabular-nums">{{ fmt(m.meanA) }} <span class="text-muted">± {{ fmt(m.spreadA) }}</span></td>
              <td class="px-3 tabular-nums">{{ fmt(m.meanB) }} <span class="text-muted">± {{ fmt(m.spreadB) }}</span></td>
              <td class="px-3 font-medium tabular-nums" :class="m.meanDelta > 0 ? 'text-success' : m.meanDelta < 0 ? 'text-danger' : ''">{{ signed(m.meanDelta) }} <span class="font-normal text-muted">± {{ fmt(m.deltaSe) }}</span></td>
              <td class="px-3 tabular-nums">{{ m.wins }} / {{ m.losses }} / {{ m.ties }}</td>
              <td class="px-3"><span class="chip" :class="verdictTone[m.verdict]"><AppIcon :name="verdictIcon[m.verdict]" :size="13" />{{ verdictText[m.verdict] }}</span></td>
            </tr>
          </tbody>
        </table>
        <p class="border-t border-line px-4 py-3 text-xs leading-5 text-muted">Spread is the standard deviation of the run-level mean across repeats (n = {{ comparison.metrics[0]?.repeatsA ?? 0 }} for A, {{ comparison.metrics[0]?.repeatsB ?? 0 }} for B). A change counts as an improvement only when the mean paired delta exceeds the larger spread.</p>
      </section>

      <section v-for="m in comparison.metrics" :key="m.metric" class="card-flat">
        <details>
          <summary class="cursor-pointer rounded-2xl px-5 py-3.5 text-sm font-semibold hover:bg-surface-2">Per-case deltas for <span class="font-mono">{{ m.metric }}</span> ({{ m.cases.length }} cases)</summary>
          <div class="scroll-thin overflow-x-auto px-5 pb-5">
            <table class="w-full text-left text-sm">
              <caption class="sr-only">Paired per-case values for {{ m.metric }}</caption>
              <thead class="eyebrow"><tr><th scope="col" class="py-2 font-semibold">Case</th><th scope="col" class="font-semibold">A</th><th scope="col" class="font-semibold">B</th><th scope="col" class="font-semibold">Δ</th><th scope="col" class="font-semibold">Result</th></tr></thead>
              <tbody>
                <tr v-for="c in [...m.cases].sort((x, y) => Math.abs(y.delta) - Math.abs(x.delta))" :key="c.caseId" class="border-t border-line">
                  <th scope="row" class="break-all py-2 pr-3 font-mono text-xs font-normal">{{ c.caseId }}</th>
                  <td class="tabular-nums">{{ fmt(c.a) }}</td><td class="tabular-nums">{{ fmt(c.b) }}</td>
                  <td class="tabular-nums" :class="c.outcome === 'win' ? 'text-success' : c.outcome === 'loss' ? 'text-danger' : 'text-muted'">
                    <span class="inline-flex items-center gap-2">{{ signed(c.delta) }}<span aria-hidden="true" class="inline-block h-1.5 w-16 overflow-hidden rounded-full bg-surface-3"><span class="block h-full rounded-full" :class="c.outcome === 'win' ? 'bg-success' : c.outcome === 'loss' ? 'bg-danger' : 'bg-line-strong'" :style="{ width: bar(c.delta) }" /></span></span>
                  </td>
                  <td>{{ c.outcome }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </details>
      </section>
    </template>
  </div>
</template>
