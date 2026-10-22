<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ProgressIndicator, ProgressRoot } from 'reka-ui'
import type { BudgetLimits, BudgetUsage } from '@/api/contracts'
import AppIcon, { type IconName } from './AppIcon.vue'

const props = defineProps<{
  limits: BudgetLimits
  usage: Partial<BudgetUsage>
  source: 'stream' | 'derived'
  /** When set and `ticking`, seconds are computed from the wall clock since this ISO time. */
  startedAt?: string
  ticking?: boolean
}>()

const now = ref(Date.now())
let timer: ReturnType<typeof setInterval> | undefined
onMounted(() => { timer = setInterval(() => (now.value = Date.now()), 1000) })
onBeforeUnmount(() => clearInterval(timer))

const elapsed = computed(() => {
  if (props.usage.seconds !== undefined) return props.usage.seconds
  if (!props.startedAt || !props.ticking) return undefined
  const t = Date.parse(props.startedAt)
  return Number.isNaN(t) ? undefined : Math.max(0, Math.round((now.value - t) / 1000))
})

interface Meter { key: string; label: string; icon: IconName; used: number | undefined; limit: number | undefined; fmt: (n: number) => string; note?: string }
const meters = computed<Meter[]>(() => [
  { key: 'steps', label: 'Steps', icon: 'activity', used: props.usage.steps, limit: props.limits.max_steps, fmt: (n) => n.toLocaleString(), note: props.source === 'derived' ? 'counted from node events' : undefined },
  { key: 'tokens', label: 'Tokens', icon: 'layers', used: props.usage.tokens, limit: props.limits.max_tokens, fmt: (n) => n.toLocaleString() },
  { key: 'usd', label: 'Cost (USD)', icon: 'dollar', used: props.usage.usd, limit: props.limits.max_usd, fmt: (n) => `$${n.toFixed(2)}` },
  { key: 'seconds', label: 'Wall-clock', icon: 'clock', used: elapsed.value, limit: props.limits.max_seconds, fmt: (n) => `${Math.round(n)}s`, note: props.usage.seconds === undefined && props.ticking ? 'client clock' : undefined },
])

const pct = (m: Meter) => (m.used !== undefined && m.limit ? Math.min(100, (m.used / m.limit) * 100) : 0)
const hot = (m: Meter) => pct(m) >= 85
</script>

<template>
  <section aria-labelledby="budget-h">
    <div class="mb-3 flex items-baseline justify-between gap-3">
      <h2 id="budget-h" class="text-sm font-semibold">Budget burn</h2>
      <p class="eyebrow">Hard limits per task</p>
    </div>
    <dl class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <div v-for="m in meters" :key="m.key" class="card p-4" :class="hot(m) ? '!border-warning/50' : ''" :data-testid="`budget-${m.key}`">
        <dt class="flex items-center gap-2 text-xs font-medium text-muted"><AppIcon :name="m.icon" :size="14" />{{ m.label }}</dt>
        <dd class="mt-2">
          <p class="flex flex-wrap items-baseline gap-x-1 tabular-nums">
            <span v-if="m.used !== undefined" class="text-2xl font-semibold tracking-tight">{{ m.fmt(m.used) }}</span>
            <span v-else class="text-sm text-muted">not reported</span>
            <span v-if="m.limit" class="text-xs text-muted"> / {{ m.fmt(m.limit) }}</span>
          </p>
          <ProgressRoot :model-value="pct(m)" :max="100" :aria-label="`${m.label} budget used`" class="mt-3 h-1.5 overflow-hidden rounded-full bg-surface-3">
            <ProgressIndicator class="h-full rounded-full transition-[width] duration-500" :class="hot(m) ? 'bg-warning' : 'bg-accent'" :style="{ width: `${pct(m)}%` }" />
          </ProgressRoot>
          <span v-if="hot(m)" class="mt-2 block text-xs font-medium text-warning">Over 85% of limit: the agent is told to wrap up.</span>
          <span v-else-if="m.note" class="mt-2 block text-xs text-muted">{{ m.note }}</span>
        </dd>
      </div>
    </dl>
  </section>
</template>
