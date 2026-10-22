<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { listRepos, registerRepo } from '@/api/repos'
import { useHistoryStore } from '@/stores/history'
import AppButton from '@/components/AppButton.vue'
import AppIcon from '@/components/AppIcon.vue'
import EmptyState from '@/components/EmptyState.vue'
import ErrorState from '@/components/ErrorState.vue'
import SnapshotCard from '@/components/SnapshotCard.vue'

const history = useHistoryStore()
const qc = useQueryClient()
// Server is the source of truth: it lists everything registered, not just what this browser did.
const repos = useQuery({ queryKey: ['repos'], queryFn: () => listRepos({ limit: 100 }) })
const router = useRouter()
const form = reactive({ name: '', source_uri: '', commit_sha: '' })
const touched = ref(false)

const errors = () => ({
  name: form.name.trim() ? '' : 'Enter a name.',
  source_uri: form.source_uri.trim() ? '' : 'Enter a git URL or a local path on the API host.',
  commit_sha: /^[0-9a-f]{7,40}$/i.test(form.commit_sha.trim()) ? '' : 'Enter a commit SHA of 7 to 40 hex characters.',
})
const register = useMutation({
  mutationFn: () => registerRepo({ name: form.name.trim(), source_uri: form.source_uri.trim(), commit_sha: form.commit_sha.trim() }),
  onSuccess: (s) => {
    history.addSnapshot({ id: s.id, name: form.name.trim(), commit: s.commit_sha })
    void qc.invalidateQueries({ queryKey: ['repos'] })
  },
})
function submit() {
  touched.value = true
  if (Object.values(errors()).some(Boolean)) return
  register.mutate()
}
const startTask = (id: string) => router.push({ name: 'new-task', query: { snapshot: id } })
</script>

<template>
  <div class="space-y-8">
    <header>
      <p class="eyebrow">Step 1</p>
      <h1 class="mt-2 text-3xl font-semibold tracking-tight">Repositories</h1>
      <p class="mt-2 max-w-2xl text-sm leading-6 text-muted">A snapshot is a repository pinned to one commit. Tasks run against a snapshot, so every answer and patch can be reproduced against the exact code the agent saw.</p>
    </header>

    <form class="card grid gap-5 p-6 md:grid-cols-3" novalidate @submit.prevent="submit">
      <div v-for="f in ([['name', 'Name', 'text', 'my-service'], ['source_uri', 'Source (git URL or path)', 'text', 'https://github.com/org/repo.git'], ['commit_sha', 'Commit SHA', 'text', '3c47104']] as const)" :key="f[0]">
        <label :for="`repo-${f[0]}`" class="block text-sm font-medium">{{ f[1] }}</label>
        <input :id="`repo-${f[0]}`" v-model="form[f[0]]" :type="f[2]" :placeholder="f[3]" spellcheck="false" autocomplete="off" class="field mt-2" :class="f[0] !== 'name' ? 'font-mono !text-[0.8rem]' : ''" :aria-invalid="touched && !!errors()[f[0]]" :aria-describedby="touched && errors()[f[0]] ? `err-${f[0]}` : undefined" />
        <p v-if="touched && errors()[f[0]]" :id="`err-${f[0]}`" role="alert" class="mt-2 text-sm text-danger">{{ errors()[f[0]] }}</p>
      </div>
      <div class="flex flex-wrap items-center gap-4 md:col-span-3">
        <AppButton variant="primary" size="lg" type="submit" :busy="register.isPending.value">Register and index</AppButton>
        <p class="text-xs text-muted">Indexing starts on the API server. Large repositories take a while; status updates below.</p>
      </div>
    </form>
    <ErrorState v-if="register.error.value" :error="register.error.value" @retry="submit()" />

    <section aria-labelledby="snaps-h" class="space-y-4">
      <h2 id="snaps-h" class="flex items-center gap-2 text-sm font-semibold"><AppIcon name="layers" :size="16" class="text-muted" />Registered snapshots <span v-if="repos.data.value" class="font-normal text-muted" data-testid="repo-total">({{ repos.data.value.total }})</span></h2>
      <p v-if="repos.isPending.value" class="text-sm text-muted" role="status">Loading repositories…</p>
      <ErrorState v-else-if="repos.error.value" :error="repos.error.value" @retry="repos.refetch()" />
      <EmptyState v-else-if="!repos.data.value?.items.length" title="No snapshots yet">Nothing is registered on this server. Register a repository above to get started.</EmptyState>
      <ul v-else class="space-y-4"><SnapshotCard v-for="s in repos.data.value.items" :id="s.id" :key="s.id" :name="s.name" :source="s.source_uri" @select="startTask" /></ul>
    </section>
  </div>
</template>
