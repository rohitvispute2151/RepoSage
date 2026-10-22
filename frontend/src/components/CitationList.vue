<script setup lang="ts">
import type { Citation } from '@/api/contracts'
import { citationHref, citationLabel } from '@/lib/citations'
import { ref } from 'vue'
import AppIcon from './AppIcon.vue'

defineProps<{ citations: Citation[] }>()
const copied = ref<number | null>(null)
async function copy(c: Citation, i: number) {
  try { await navigator.clipboard.writeText(citationLabel(c)); copied.value = i } catch { copied.value = null }
}
</script>

<template>
  <ol class="grid gap-3 md:grid-cols-2" data-testid="citations">
    <li v-for="(c, i) in citations" :id="`cite-${i + 1}`" :key="i" class="card-flat group flex gap-3 p-4 transition-colors hover:border-accent/50">
      <span class="grid size-7 shrink-0 place-items-center rounded-lg bg-accent-soft text-xs font-semibold tabular-nums text-accent" aria-hidden="true">{{ i + 1 }}</span>
      <div class="min-w-0 flex-1">
        <p class="text-sm">
          <span class="sr-only">[{{ i + 1 }}] </span>
          <a v-if="citationHref(c)" :href="citationHref(c)!" target="_blank" rel="noopener noreferrer nofollow" class="link inline-flex items-center gap-1.5 break-all font-mono text-[0.82rem]">{{ citationLabel(c) }}<AppIcon name="external" :size="13" /><span class="sr-only"> (opens source in a new tab)</span></a>
          <code v-else class="break-all text-[0.82rem]">{{ citationLabel(c) }}</code>
        </p>
        <p class="mt-1.5 text-xs text-muted">Symbol <code class="break-all rounded bg-surface-3 px-1.5 py-0.5 text-fg">{{ c.symbol }}</code>, lines {{ c.start_line }} to {{ c.end_line }}</p>
        <button v-if="!citationHref(c)" type="button" class="link mt-2 inline-flex items-center gap-1.5 text-xs" @click="copy(c, i)"><AppIcon name="copy" :size="13" />{{ copied === i ? 'Copied' : 'Copy location' }}</button>
      </div>
    </li>
  </ol>
</template>
