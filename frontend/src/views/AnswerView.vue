<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useTask } from '@/composables/useTask'
import { answerState, unwrapAnswer } from '@/lib/citations'
import CitationList from '@/components/CitationList.vue'
import AppIcon from '@/components/AppIcon.vue'
import EmptyState from '@/components/EmptyState.vue'

const route = useRoute()
const id = computed(() => String(route.params.id))
const { data: task } = useTask(id)
const r = computed(() => task.value?.result ?? null)
const state = computed(() => (r.value ? answerState(r.value) : null))
const shown = computed(() => unwrapAnswer(r.value?.answer, r.value?.found).answer)
</script>

<template>
  <div class="space-y-6">
    <EmptyState v-if="task?.mode === 'fix'" title="No answer for a fix task">Fix tasks produce patches. Open Patch review.</EmptyState>
    <EmptyState v-else-if="!task || ['queued', 'running'].includes(task.status)" title="The answer is not ready">
      The agent is still gathering evidence. This page updates when it finishes.
    </EmptyState>
    <EmptyState v-else-if="['failed', 'cancelled', 'approval_timeout'].includes(task.status) && !r" :title="`The task ${task.status.replaceAll('_', ' ')} before answering`">No answer was produced.</EmptyState>
    <p v-else-if="task.resultProblem" role="alert" class="rounded-2xl border border-danger/30 bg-danger-bg px-4 py-3 text-sm text-danger">The result could not be read: {{ task.resultProblem }}</p>
    <EmptyState v-else-if="!r" title="No result stored" />

    <template v-else>
      <p v-if="task?.status === 'budget_exceeded'" class="flex items-center gap-2 rounded-2xl border border-warning/40 bg-warning-bg px-4 py-3 text-sm text-warning" role="status"><AppIcon name="alert" :size="16" />The budget ran out, so this is a partial report.</p>

      <section v-if="state === 'not-found'" class="rounded-2xl border border-warning/40 bg-warning-bg p-6 text-warning" data-testid="not-found" aria-labelledby="nf-h">
        <div class="flex gap-3">
          <AppIcon name="search" :size="22" class="mt-0.5" />
          <div class="min-w-0">
            <h2 id="nf-h" class="font-semibold">The agent could not find an answer in this repository</h2>
            <p class="mt-1 text-sm leading-6">It had too little evidence to answer without guessing. Nothing below is a verified claim.</p>
            <p v-if="shown && shown !== 'Unable to locate answer.'" class="mt-4 whitespace-pre-wrap rounded-xl bg-surface p-4 text-sm leading-6 text-fg">{{ shown }}</p>
          </div>
        </div>
      </section>

      <section v-else class="card relative overflow-hidden p-6 sm:p-8" aria-labelledby="ans-h" data-testid="answer">
        <div class="absolute inset-y-0 left-0 w-1 bg-accent" aria-hidden="true" />
        <h2 id="ans-h" class="eyebrow">Answer</h2>
        <!-- Model output is untrusted: rendered as text only, never as markup. -->
        <p class="mt-4 max-w-3xl whitespace-pre-wrap text-[1.05rem] leading-8" data-testid="answer-text">{{ shown }}</p>
        <p v-if="state === 'uncited'" class="mt-5 flex items-center gap-2 rounded-xl bg-warning-bg px-3 py-2 text-sm text-warning" data-testid="uncited"><AppIcon name="alert" :size="16" />No citation survived verification. Treat this answer as unverified.</p>
      </section>

      <section aria-labelledby="cit-h">
        <h2 id="cit-h" class="mb-3 flex items-center gap-2 text-sm font-semibold"><AppIcon name="shield" :size="16" class="text-accent" />Citations <span class="font-normal text-muted">({{ r.citations.length }} verified against the snapshot)</span></h2>
        <CitationList v-if="r.citations.length" :citations="r.citations" />
        <EmptyState v-else title="No verified citations" />
      </section>

      <section v-if="r.notes.length" aria-labelledby="notes-h" class="card-flat p-5">
        <h2 id="notes-h" class="text-sm font-semibold">Notes from the verifier</h2>
        <ul class="mt-3 list-disc space-y-1.5 pl-5 text-sm text-muted"><li v-for="(n, i) in r.notes" :key="i" class="break-words">{{ n }}</li></ul>
      </section>
    </template>
  </div>
</template>
