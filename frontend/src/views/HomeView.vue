<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useQuery } from '@tanstack/vue-query'
import { fetchHealth, fetchReadiness } from '@/api/health'
import { useSessionStore } from '@/stores/session'
import { useHistoryStore } from '@/stores/history'
import AppButton from '@/components/AppButton.vue'
import AppIcon from '@/components/AppIcon.vue'
import EmptyState from '@/components/EmptyState.vue'

const session = useSessionStore()
const history = useHistoryStore()
const router = useRouter()
const taskId = ref('')
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const invalid = ref(false)

const live = useQuery({ queryKey: ['healthz'], queryFn: fetchHealth, refetchInterval: 15000, retry: false })
const ready = useQuery({ queryKey: ['readyz'], queryFn: fetchReadiness, refetchInterval: 15000, retry: false })

function open() {
  const id = taskId.value.trim()
  invalid.value = !UUID.test(id)
  if (!invalid.value) void router.push({ name: 'trajectory', params: { id } })
}
const when = (iso: string) => new Date(iso).toLocaleString()
</script>

<template>
  <div class="space-y-10">
    <section class="relative">
      <!-- Decorative sample of a verified patch. Hidden from assistive tech; not real data. -->
      <div class="pointer-events-none absolute right-0 top-0 hidden w-[22.5rem] select-none min-[1360px]:block" aria-hidden="true">
        <div class="card rotate-[1.5deg] overflow-hidden !shadow-[var(--shadow-pop)]">
          <div class="flex items-center justify-between border-b border-line bg-surface-2 px-4 py-2.5">
            <span class="flex items-center gap-2 font-mono text-xs"><AppIcon name="file" :size="13" class="text-muted" />src/pkg/http.py</span>
            <span class="eyebrow !text-[0.6rem]">Illustrative example</span>
          </div>
          <div class="font-mono text-[0.72rem] leading-6">
            <p class="bg-info-bg px-4 text-info">@@ def compute_backoff(attempt, base=0.5)</p>
            <p class="bg-danger-bg px-4"><span class="mr-3 font-bold text-danger">-</span><span class="tok-kw">return</span> base * 2 * attempt</p>
            <p class="bg-success-bg px-4"><span class="mr-3 font-bold text-success">+</span><span class="tok-kw">return</span> base * 2 ** attempt</p>
          </div>
          <div class="space-y-2.5 border-t border-line p-4">
            <p class="flex items-center gap-2 text-xs text-success"><AppIcon name="check" :size="14" />Target tests pass in the sandbox</p>
            <p class="flex items-center gap-2 text-xs text-success"><AppIcon name="check" :size="14" />No test files touched</p>
            <div class="flex gap-2 pt-1.5">
              <span class="flex-1 rounded-[10px] bg-accent py-2 text-center text-xs font-semibold text-accent-fg">Approve…</span>
              <span class="rounded-[10px] border border-line-strong px-3 py-2 text-xs text-muted">Edit</span>
              <span class="rounded-[10px] border border-danger/35 bg-danger-bg px-3 py-2 text-xs text-danger">Reject</span>
            </div>
          </div>
        </div>
      </div>
      <p class="eyebrow flex items-center gap-2"><span class="inline-block h-px w-6 bg-accent" aria-hidden="true" />Agentic codebase assistant</p>
      <h1 class="mt-4 max-w-[40rem] text-4xl font-semibold leading-[1.08] tracking-tight sm:text-5xl">
        Fixes you can <span class="rounded-lg bg-accent-soft px-2 text-accent">verify</span>.<br class="hidden sm:block" /> Answers you can cite.
      </h1>
      <p class="mt-5 max-w-2xl text-base leading-7 text-muted min-[1360px]:max-w-xl">
        RepoSage investigates a repository, proves each patch in a sandbox, and stops for your decision before anything is applied. This console is where you watch the agent work and make that call.
      </p>

      <section aria-labelledby="status-h" class="card mt-7 inline-flex flex-wrap items-center gap-3 !rounded-full py-2 pl-4 pr-3" data-testid="api-status">
        <h2 id="status-h" class="eyebrow">API</h2>
        <span v-if="live.isError.value" class="chip bg-danger-bg text-danger"><span class="live-dot still" aria-hidden="true" />Unreachable</span>
        <span v-else-if="live.isPending.value" class="text-sm text-muted" role="status">Checking…</span>
        <template v-else>
          <span class="chip bg-success-bg text-success"><span class="live-dot" aria-hidden="true" />Live</span>
          <span v-if="ready.data.value?.status === 'ready'" class="chip bg-success-bg text-success"><AppIcon name="check" :size="13" />Database ready</span>
          <span v-else-if="ready.data.value" class="chip bg-warning-bg text-warning"><AppIcon name="alert" :size="13" />Database not ready</span>
        </template>
        <p v-if="live.isError.value" class="pr-2 text-sm text-muted">Nothing will load until the API answers. Start it, or run <code class="rounded bg-surface-3 px-1.5 py-0.5 text-xs text-fg">bun run mock</code> for a scripted demo.</p>
      </section>
    </section>

    <ol class="grid gap-4 md:grid-cols-3" aria-label="Getting started">
      <li v-for="(s, n) in [
        { to: '/repos', icon: 'repo', title: 'Register a repository', body: 'Index a repo at a pinned commit.' },
        { to: '/tasks/new', icon: 'plus', title: 'Create a task', body: 'Ask a question or fix failing tests.' },
        { to: '/evals/compare', icon: 'chart', title: 'Compare eval runs', body: 'Paired deltas with run-to-run spread.' },
      ] as const" :key="s.to">
        <RouterLink :to="s.to" class="card group relative flex h-full flex-col gap-3 p-5 transition duration-200 hover:-translate-y-0.5 hover:border-accent/50">
          <span class="flex items-center justify-between">
            <span class="grid size-10 place-items-center rounded-xl bg-surface-3 text-accent transition group-hover:bg-accent group-hover:text-accent-fg"><AppIcon :name="s.icon" :size="19" /></span>
            <span class="font-mono text-xs text-muted" aria-hidden="true">0{{ n + 1 }}</span>
          </span>
          <span class="font-semibold tracking-tight">{{ n + 1 }}. {{ s.title }}</span>
          <span class="text-sm leading-6 text-muted">{{ s.body }}</span>
          <AppIcon name="arrow" :size="16" class="mt-auto text-muted transition group-hover:translate-x-1 group-hover:text-accent" />
        </RouterLink>
      </li>
    </ol>

    <div class="grid gap-6 lg:grid-cols-5">
      <section aria-labelledby="open-h" class="space-y-3 lg:col-span-2">
        <h2 id="open-h" class="text-sm font-semibold">Connect and open a task</h2>
        <form class="card space-y-5 p-5" novalidate @submit.prevent="open">
          <div>
            <label for="api-key" class="flex items-center gap-2 text-sm font-medium"><AppIcon name="key" :size="14" class="text-muted" />API key</label>
            <input id="api-key" v-model="session.apiKey" type="password" autocomplete="off" class="field mt-2" aria-describedby="key-help" />
            <p id="key-help" class="mt-2 text-xs leading-5 text-muted">Sent as X-API-Key on every request. Defaults to the dev key in dev builds; stored in this browser only.</p>
          </div>
          <div>
            <label for="task-id" class="flex items-center gap-2 text-sm font-medium"><AppIcon name="hash" :size="14" class="text-muted" />Task id</label>
            <input id="task-id" v-model="taskId" type="text" autocomplete="off" spellcheck="false" placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" class="field mt-2 font-mono !text-xs" :aria-invalid="invalid" :aria-describedby="invalid ? 'task-err' : undefined" />
            <p v-if="invalid" id="task-err" role="alert" class="mt-2 text-sm text-danger">Enter a task id in UUID form.</p>
          </div>
          <AppButton variant="primary" type="submit" size="lg" class="w-full">Open task<AppIcon name="arrow" :size="16" /></AppButton>
        </form>
      </section>

      <section aria-labelledby="recent-h" class="space-y-3 lg:col-span-3">
        <div class="flex items-center justify-between">
          <h2 id="recent-h" class="text-sm font-semibold">Recent tasks</h2>
          <button v-if="history.tasks.length || history.snapshots.length" type="button" class="text-xs text-muted underline underline-offset-4 hover:text-fg" @click="history.clear()">Clear history</button>
        </div>
        <EmptyState v-if="!history.tasks.length" title="No tasks yet">The API has no list endpoint, so tasks you create or open in this browser appear here.</EmptyState>
        <ul v-else class="card divide-y divide-line overflow-hidden" data-testid="recent-tasks">
          <li v-for="t in history.tasks" :key="t.id">
            <RouterLink :to="{ name: 'trajectory', params: { id: t.id } }" class="group flex items-center gap-4 px-5 py-3.5 transition hover:bg-surface-2">
              <span class="grid size-9 shrink-0 place-items-center rounded-xl bg-surface-3 text-muted group-hover:text-accent"><AppIcon :name="t.mode === 'fix' ? 'wrench' : 'chat'" :size="17" /></span>
              <span class="min-w-0 flex-1">
                <span class="flex items-center gap-2"><span class="truncate text-sm font-medium">{{ t.label }}</span><span class="chip !px-2 !py-0 !text-[0.65rem] bg-surface-3 text-muted">{{ t.mode }}</span></span>
                <span class="block break-all font-mono text-xs text-muted">{{ t.id }} · {{ when(t.at) }}</span>
              </span>
              <AppIcon name="arrow" :size="15" class="text-muted transition group-hover:translate-x-0.5 group-hover:text-accent" />
            </RouterLink>
          </li>
        </ul>
      </section>
    </div>
  </div>
</template>
