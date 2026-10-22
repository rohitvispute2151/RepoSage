<script setup lang="ts">
import { computed } from 'vue'
import { parseUnifiedDiff } from '@/lib/diff'
import { highlightPython, isPython } from '@/lib/highlight'
import AppIcon from './AppIcon.vue'
import EmptyState from './EmptyState.vue'

const props = defineProps<{ diff: string }>()
const files = computed(() => parseUnifiedDiff(props.diff))
const sign = { add: '+', del: '-', ctx: ' ', hunk: '', meta: '' } as const
const segments = (path: string, kind: string, text: string) =>
  isPython(path) && (kind === 'add' || kind === 'del' || kind === 'ctx') ? highlightPython(text) : [{ text }]
</script>

<template>
  <EmptyState v-if="!diff.trim()" title="The patch is empty" />
  <div v-else class="space-y-5" data-testid="diff-viewer">
    <!-- Every diff line is interpolated as text. Repo and model content never reaches the DOM as markup. -->
    <section v-for="(f, i) in files" :key="i" class="overflow-hidden rounded-2xl border border-line bg-surface shadow-[var(--shadow)]" :aria-label="`Changes in ${f.path}`">
      <h3 class="flex flex-wrap items-center justify-between gap-2 border-b border-line bg-surface-2 px-4 py-2.5 font-mono text-[0.8rem]">
        <span class="flex min-w-0 items-center gap-2"><AppIcon name="file" :size="15" class="text-muted" /><span class="break-all">{{ f.path }}</span></span>
        <span class="flex items-center gap-2 text-xs font-semibold tabular-nums">
          <span class="text-success">+{{ f.added }}</span><span class="text-danger">−{{ f.removed }}</span>
          <span aria-hidden="true" class="flex gap-px"><i v-for="k in 5" :key="k" class="block size-2 rounded-[2px]" :class="k <= Math.round((f.added / Math.max(1, f.added + f.removed)) * 5) ? 'bg-success' : 'bg-danger'" /></span>
        </span>
      </h3>
      <div class="scroll-thin overflow-x-auto">
        <table role="presentation" class="w-full border-collapse font-mono text-[0.78rem] leading-6">
          <tbody>
            <tr
              v-for="(l, j) in f.lines"
              :key="j"
              :data-kind="l.kind"
              :class="{
                'bg-success-bg': l.kind === 'add',
                'bg-danger-bg': l.kind === 'del',
                'bg-info-bg text-info': l.kind === 'hunk',
                'text-muted': l.kind === 'meta',
                'text-[0.7rem]': l.kind === 'meta',
              }"
            >
              <td class="w-11 select-none border-r border-line/60 px-2 text-right tabular-nums text-muted" aria-hidden="true">{{ l.oldNo ?? '' }}</td>
              <td class="w-11 select-none border-r border-line/60 px-2 text-right tabular-nums text-muted" aria-hidden="true">{{ l.newNo ?? '' }}</td>
              <td class="whitespace-pre pr-4">
                <span class="sr-only">{{ l.kind === 'add' ? 'Added: ' : l.kind === 'del' ? 'Removed: ' : '' }}</span>
                <span aria-hidden="true" class="inline-block w-5 select-none text-center font-bold" :class="l.kind === 'add' ? 'text-success' : l.kind === 'del' ? 'text-danger' : ''">{{ sign[l.kind] }}</span><span v-for="(s, k) in segments(f.path, l.kind, l.text)" :key="k" :class="s.cls ? `tok-${s.cls}` : ''">{{ s.text }}</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>
