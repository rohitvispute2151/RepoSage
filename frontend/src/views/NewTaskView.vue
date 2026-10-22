<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useMutation, useQuery } from '@tanstack/vue-query'
import { listRepos } from '@/api/repos'
import { createTask, type TaskCreate } from '@/api/tasks'
import { useHistoryStore } from '@/stores/history'
import AppButton from '@/components/AppButton.vue'
import AppIcon from '@/components/AppIcon.vue'
import ErrorState from '@/components/ErrorState.vue'
import SnapshotCard from '@/components/SnapshotCard.vue'

const route = useRoute()
const router = useRouter()
const history = useHistoryStore()
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const NODEID = /^[\w./-]+\.py(::[\w[\]\-.,]+)*$/

const repos = useQuery({ queryKey: ['repos'], queryFn: () => listRepos({ limit: 100 }) })
// Offer what the server has registered; fall back to this browser's history if the list is unavailable.
const options = computed(() => {
  const server = (repos.data.value?.items ?? []).map((r) => ({ id: r.id, label: `${r.name} @ ${r.commit_sha} (${r.status})` }))
  return server.length ? server : history.snapshots.map((h) => ({ id: h.id, label: h.name }))
})

const mode = ref<'qa' | 'fix'>('qa')
const snapshot = ref(typeof route.query.snapshot === 'string' ? route.query.snapshot : history.snapshots[0]?.id ?? '')
const question = ref('')
const description = ref('')
const failingTests = ref('')
const budgets = reactive({ max_steps: 30, max_tokens: 250000, max_usd: 1, max_seconds: 900 })
const touched = ref(false)

const tests = computed(() => failingTests.value.split('\n').map((l) => l.trim()).filter(Boolean))
const errors = computed(() => {
  const e: Record<string, string> = {}
  if (!UUID.test(snapshot.value.trim())) e.snapshot = 'Choose or paste a snapshot id (UUID).'
  if (mode.value === 'qa' && (question.value.trim().length < 3 || question.value.length > 2000)) e.question = 'Ask a question of 3 to 2000 characters.'
  if (mode.value === 'fix') {
    if (!tests.value.length || tests.value.length > 20) e.tests = 'List 1 to 20 failing pytest node ids, one per line.'
    else if (tests.value.some((t) => !NODEID.test(t))) e.tests = 'Each line must be a pytest node id like tests/test_x.py::test_name (no flags or spaces).'
    if (description.value.length > 4000) e.description = 'Keep the description under 4000 characters.'
  }
  if (budgets.max_steps < 1 || budgets.max_steps > 60) e.max_steps = '1 to 60'
  if (budgets.max_tokens < 1000 || budgets.max_tokens > 1_000_000) e.max_tokens = '1,000 to 1,000,000'
  if (!(budgets.max_usd > 0) || budgets.max_usd > 5) e.max_usd = 'Above 0, up to 5'
  if (budgets.max_seconds < 30 || budgets.max_seconds > 3600) e.max_seconds = '30 to 3600'
  return e
})

const create = useMutation({
  mutationFn: () => {
    const body: TaskCreate = {
      snapshot_id: snapshot.value.trim(),
      mode: mode.value,
      budgets: { ...budgets },
      ...(mode.value === 'qa' ? { qa: { question: question.value.trim() } } : { fix: { description: description.value, failing_tests: tests.value } }),
    }
    return createTask(body)
  },
  onSuccess: (t) => {
    history.addTask({ id: t.id, mode: t.mode, label: mode.value === 'qa' ? question.value.trim().slice(0, 60) : tests.value[0] ?? 'Fix' })
    void router.push({ name: 'trajectory', params: { id: t.id } })
  },
})
function submit() {
  touched.value = true
  if (Object.keys(errors.value).length) return
  create.mutate()
}
const fieldClass = 'field mt-2'
</script>

<template>
  <div class="mx-auto max-w-3xl space-y-8">
    <header>
      <p class="eyebrow">Step 2</p>
      <h1 class="mt-2 text-3xl font-semibold tracking-tight">New task</h1>
      <p class="mt-2 text-sm leading-6 text-muted">Ask about the code, or hand the agent failing tests and review the patch it proves.</p>
    </header>
    <form class="card space-y-7 p-6" novalidate @submit.prevent="submit">
      <fieldset>
        <legend class="text-sm font-medium">Mode</legend>
        <div class="mt-3 grid gap-3 sm:grid-cols-2">
          <label v-for="m in ([
            { v: 'qa', icon: 'chat', title: 'Question about the code', body: 'Cited answers, checked against the snapshot.' },
            { v: 'fix', icon: 'wrench', title: 'Fix failing tests', body: 'A sandbox-verified patch that waits for your approval.' },
          ] as const)" :key="m.v" class="mode-card relative flex cursor-pointer focus-within:outline focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-[var(--focus)] gap-3 rounded-2xl border border-line-strong bg-surface-2 p-4 transition hover:border-accent/50" :class="mode === m.v ? '!border-accent bg-accent-soft' : ''">
            <input v-model="mode" type="radio" :value="m.v" class="absolute inset-0 size-full cursor-pointer opacity-0" />
            <span class="grid size-10 shrink-0 place-items-center rounded-xl" :class="mode === m.v ? 'bg-accent text-accent-fg' : 'bg-surface-3 text-muted'"><AppIcon :name="m.icon" :size="19" /></span>
            <span>
              <span class="block text-sm font-semibold">{{ m.title }}</span>
              <span class="mt-0.5 block text-xs leading-5 text-muted">{{ m.body }}</span>
            </span>
          </label>
        </div>
      </fieldset>

      <div>
        <label for="t-snap" class="block text-sm font-medium">Snapshot id</label>
        <input id="t-snap" v-model="snapshot" list="snap-list" spellcheck="false" autocomplete="off" :class="[fieldClass, 'font-mono !text-[0.8rem]']" :aria-invalid="touched && !!errors.snapshot" :aria-describedby="touched && errors.snapshot ? 'e-snap' : undefined" />
        <datalist id="snap-list"><option v-for="o in options" :key="o.id" :value="o.id">{{ o.label }}</option></datalist>
        <p v-if="touched && errors.snapshot" id="e-snap" role="alert" class="mt-2 text-sm text-danger">{{ errors.snapshot }}</p>
        <p v-else class="mt-2 text-xs text-muted">Register one on <RouterLink to="/repos" class="link">Repositories</RouterLink>.</p>
      </div>
      <ul v-if="/^[0-9a-f-]{36}$/i.test(snapshot.trim())"><SnapshotCard :id="snapshot.trim()" /></ul>

      <div v-if="mode === 'qa'">
        <label for="t-q" class="block text-sm font-medium">Question</label>
        <textarea id="t-q" v-model="question" rows="3" maxlength="2000" :class="fieldClass" placeholder="Where is retry backoff computed?" :aria-invalid="touched && !!errors.question" :aria-describedby="touched && errors.question ? 'e-q' : undefined" />
        <p v-if="touched && errors.question" id="e-q" role="alert" class="mt-2 text-sm text-danger">{{ errors.question }}</p>
      </div>
      <template v-else>
        <div>
          <label for="t-tests" class="block text-sm font-medium">Failing tests (pytest node ids, one per line)</label>
          <textarea id="t-tests" v-model="failingTests" rows="4" spellcheck="false" :class="[fieldClass, 'font-mono !text-[0.8rem]']" placeholder="tests/test_http.py::test_retry" :aria-invalid="touched && !!errors.tests" :aria-describedby="touched && errors.tests ? 'e-tests' : undefined" />
          <p v-if="touched && errors.tests" id="e-tests" role="alert" class="mt-2 text-sm text-danger">{{ errors.tests }}</p>
        </div>
        <div>
          <label for="t-desc" class="block text-sm font-medium">Description <span class="font-normal text-muted">(optional)</span></label>
          <textarea id="t-desc" v-model="description" rows="3" maxlength="4000" :class="fieldClass" />
        </div>
      </template>

      <fieldset>
        <legend class="text-sm font-medium">Budgets <span class="font-normal text-muted">(hard limits; the agent stops and reports when one is hit)</span></legend>
        <div class="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div v-for="b in ([['max_steps', 'Steps'], ['max_tokens', 'Tokens'], ['max_usd', 'USD'], ['max_seconds', 'Seconds']] as const)" :key="b[0]">
            <label :for="`b-${b[0]}`" class="block text-xs text-muted">{{ b[1] }}</label>
            <input :id="`b-${b[0]}`" v-model.number="budgets[b[0]]" type="number" step="any" :class="[fieldClass, 'tabular-nums']" :aria-invalid="touched && !!errors[b[0]]" />
            <p v-if="touched && errors[b[0]]" role="alert" class="mt-1 text-xs text-danger">{{ errors[b[0]] }}</p>
          </div>
        </div>
      </fieldset>

      <ErrorState v-if="create.error.value" :error="create.error.value" @retry="submit()" />
      <AppButton variant="primary" size="lg" type="submit" :busy="create.isPending.value">Create task<AppIcon name="arrow" :size="16" /></AppButton>
    </form>
  </div>
</template>
