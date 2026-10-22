<script setup lang="ts">
import AppIcon from './AppIcon.vue'

defineProps<{ nodes: ReadonlyArray<{ node: string; visits: number; state: 'pending' | 'active' | 'done' }> }>()
</script>

<template>
  <section aria-labelledby="nodes-h" class="card p-5">
    <div class="flex items-baseline justify-between gap-3">
      <h2 id="nodes-h" class="text-sm font-semibold">Node progress</h2>
      <p class="eyebrow">Agent graph</p>
    </div>
    <ol class="mt-5 flex flex-col gap-4 sm:flex-row sm:gap-0" data-testid="node-stepper">
      <li
        v-for="(n, i) in nodes"
        :key="n.node"
        class="step relative flex items-center gap-3 sm:flex-1 sm:flex-col sm:gap-2.5"
        :class="{ 'is-last': i === nodes.length - 1, 'is-done': n.state === 'done' }"
        :data-node="n.node"
        :data-state="n.state"
      >
        <span
          class="relative z-10 grid size-8 place-items-center rounded-full border text-xs font-semibold tabular-nums transition-colors"
          :class="{
            'border-line-strong bg-surface text-muted': n.state === 'pending',
            'node-active border-info bg-info-bg text-info': n.state === 'active',
            'border-transparent bg-accent text-accent-fg': n.state === 'done',
          }"
        >
          <AppIcon v-if="n.state === 'done'" name="check" :size="15" />
          <template v-else>{{ i + 1 }}</template>
        </span>
        <span class="text-sm font-medium sm:text-center" :class="n.state === 'pending' ? 'text-muted' : 'text-fg'">
          {{ n.node }}
          <span v-if="n.visits > 1" class="text-xs text-muted">×{{ n.visits }}</span>
          <span class="sr-only"> — {{ n.state === 'pending' ? 'not started' : n.state === 'active' ? 'in progress' : 'finished' }}</span>
        </span>
      </li>
    </ol>
  </section>
</template>

<style scoped>
/* connector from this node's circle to the next one */
@media (min-width: 640px) {
  .step:not(.is-last)::after {
    content: '';
    position: absolute;
    top: 15px;
    left: calc(50% + 22px);
    right: calc(-50% + 22px);
    height: 2px;
    border-radius: 2px;
    background: var(--border-strong);
  }
  .step.is-done:not(.is-last)::after { background: var(--accent); }
}
@media (max-width: 639px) {
  .step:not(.is-last)::after {
    content: '';
    position: absolute;
    left: 15px;
    top: 38px;
    bottom: -18px;
    width: 2px;
    background: var(--border-strong);
  }
  .step.is-done:not(.is-last)::after { background: var(--accent); }
}
</style>
