<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { TabsContent, TabsList, TabsRoot, TabsTrigger } from 'reka-ui'
import { useMutation, useQueryClient } from '@tanstack/vue-query'
import { ApiError } from '@/api/errors'
import { submitApproval, type Decision } from '@/api/tasks'
import type { PendingPatch } from '@/stores/trajectory'
import { parseUnifiedDiff } from '@/lib/diff'
import AppButton from './AppButton.vue'
import ConfirmDialog from './ConfirmDialog.vue'
import DiffViewer from './DiffViewer.vue'
import AppIcon from './AppIcon.vue'
import ErrorState from './ErrorState.vue'
import TestEvidence from './TestEvidence.vue'

const props = defineProps<{ taskId: string; pending: PendingPatch; canDecide: boolean; blockedReason?: string }>()
const emit = defineEmits<{ refetch: [] }>()

const qc = useQueryClient()
const confirmApprove = ref(false)
const confirmReject = ref(false)
const stale = ref(false)
const needsRefetch = ref(false)
const allowed = computed(() => props.canDecide && !needsRefetch.value)
const editing = ref(false)
const editedDiff = ref('')
const comment = ref('')
const sent = ref<Decision['decision'] | null>(null)
const failure = ref<unknown>(null)

const stats = computed(() => {
  const files = parseUnifiedDiff(props.pending.diff)
  return { files: files.length, added: files.reduce((a, f) => a + f.added, 0), removed: files.reduce((a, f) => a + f.removed, 0) }
})
const evidenceOk = computed(() => {
  const e = props.pending.test_evidence
  return !!e && e.all_target_pass === true && e.policy_ok === true && (e.regressions ?? 0) === 0
})

const mutation = useMutation({
  // The sha sent is always the pending patch's own hash; callers only choose the decision.
  mutationFn: (d: Decision) => submitApproval(props.taskId, props.pending, d),
  onSuccess: (_r, d) => {
    sent.value = d.decision
    failure.value = null
    confirmApprove.value = false
    confirmReject.value = false
    editing.value = false
    void qc.invalidateQueries({ queryKey: ['task', props.taskId] })
  },
  onError: (e) => {
    confirmApprove.value = false
    confirmReject.value = false
    if (e instanceof ApiError && e.kind === 'conflict') { stale.value = true; needsRefetch.value = true }
    else failure.value = e
  },
})
const staleDetail = computed(() => (mutation.error.value instanceof ApiError ? mutation.error.value.message : ''))

function startEdit() { editedDiff.value = props.pending.diff; editing.value = true }
const editChanged = computed(() => editedDiff.value.trim() !== '' && editedDiff.value !== props.pending.diff)
function sendEdit() { mutation.mutate({ decision: 'edit', editedDiff: editedDiff.value, comment: comment.value || undefined }) }
watch(() => props.pending.sha256, () => { needsRefetch.value = false; sent.value = null })
function doRefetch() { stale.value = false; needsRefetch.value = false; sent.value = null; editing.value = false; mutation.reset(); emit('refetch') }

const labels = { approve: 'approved', reject: 'rejected', edit: 'edited' } as const
</script>

<template>
  <section aria-labelledby="review-h" class="space-y-6" data-testid="approval-panel" :data-sha="pending.sha256">
    <div class="card flex flex-wrap items-start justify-between gap-4 p-5">
      <div class="flex min-w-0 gap-4">
        <span class="grid size-11 shrink-0 place-items-center rounded-xl bg-accent-soft text-accent"><AppIcon name="shield" :size="22" /></span>
        <div class="min-w-0">
          <h2 id="review-h" class="text-xl font-semibold tracking-tight">Proposed patch</h2>
          <p class="mt-0.5 text-sm text-muted">{{ stats.files }} file(s), <span class="font-semibold text-success">+{{ stats.added }}</span> / <span class="font-semibold text-danger">−{{ stats.removed }}</span></p>
          <p class="mt-2 flex max-w-full flex-wrap items-center gap-2 text-xs text-muted">Patch hash <span class="hash-chip"><AppIcon name="hash" :size="12" /><code class="break-all" data-testid="patch-sha">{{ pending.sha256 }}</code></span></p>
        </div>
      </div>
      <p v-if="evidenceOk" class="chip bg-success-bg text-success ring-1 ring-inset ring-success/30"><AppIcon name="check" :size="14" />Tests pass in the sandbox</p>
      <p v-else class="chip bg-warning-bg text-warning ring-1 ring-inset ring-warning/35"><AppIcon name="alert" :size="14" />Test evidence incomplete or failing</p>
    </div>

    <TabsRoot default-value="diff">
      <TabsList aria-label="Patch details" class="inline-flex gap-1 rounded-xl border border-line bg-surface-2 p-1">
        <TabsTrigger v-for="t in [['diff', 'Diff'], ['tests', 'Test evidence'], ['why', 'Rationale']]" :key="t[0]" :value="t[0]!" class="rounded-lg px-4 py-1.5 text-sm font-medium text-muted transition hover:text-fg data-[state=active]:bg-surface data-[state=active]:text-fg data-[state=active]:shadow-[var(--shadow)]">{{ t[1] }}</TabsTrigger>
      </TabsList>
      <TabsContent value="diff" class="pt-5">
        <template v-if="!editing"><DiffViewer :diff="pending.diff" /></template>
        <div v-else class="card space-y-3 p-5">
          <label for="edit-diff" class="block text-sm font-medium">Edit the unified diff</label>
          <textarea id="edit-diff" v-model="editedDiff" spellcheck="false" rows="16" class="field scroll-thin font-mono !text-xs leading-5" />
          <p class="text-sm text-muted">The backend re-validates an edited patch (no test files, size limits) and re-runs it in the sandbox before anything is applied.</p>
        </div>
      </TabsContent>
      <TabsContent value="tests" class="pt-5"><TestEvidence :evidence="pending.test_evidence" /></TabsContent>
      <TabsContent value="why" class="pt-5">
        <div class="card p-5">
          <p v-if="pending.rationale" class="whitespace-pre-wrap text-sm leading-7">{{ pending.rationale }}</p>
          <p v-else class="text-sm text-muted">The agent gave no rationale.</p>
        </div>
      </TabsContent>
    </TabsRoot>

    <ErrorState v-if="failure" :error="failure" @retry="failure = null" />

    <div v-if="sent" role="status" class="flex items-center gap-3 rounded-2xl border border-success/30 bg-success-bg px-4 py-3 text-sm text-success" data-testid="decision-sent">
      <AppIcon name="check" :size="18" />
      <span>Decision sent: patch {{ labels[sent] }}. Waiting for the worker to resume the task.</span>
    </div>
    <div v-else class="decision-bar card z-20 md:sticky md:bottom-4 space-y-3 p-4 !shadow-[var(--shadow-pop)] backdrop-blur">
      <p v-if="needsRefetch" class="flex flex-wrap items-center gap-3 rounded-xl bg-warning-bg px-3 py-2 text-sm text-warning" data-testid="blocked-reason">Your last decision was rejected as stale. Refetch before deciding again.<AppButton @click="doRefetch">Refetch latest patch</AppButton></p>
      <p v-else-if="!canDecide" class="rounded-xl bg-surface-3 px-3 py-2 text-sm" data-testid="blocked-reason">{{ blockedReason }}</p>
      <div class="flex flex-wrap items-end gap-3">
        <div class="min-w-[14rem] flex-1">
          <label for="decision-comment" class="block text-xs font-medium">Comment <span class="font-normal text-muted">(optional, stored with the decision)</span></label>
          <input id="decision-comment" v-model="comment" type="text" maxlength="500" class="field mt-1.5" />
        </div>
        <div class="flex flex-wrap gap-2" role="group" aria-label="Decision">
          <template v-if="!editing">
            <AppButton variant="primary" size="lg" :disabled="!allowed" data-testid="approve" @click="confirmApprove = true"><AppIcon name="check" :size="16" />Approve…</AppButton>
            <AppButton size="lg" :disabled="!allowed" data-testid="edit" @click="startEdit"><AppIcon name="pencil" :size="15" />Edit patch</AppButton>
            <AppButton variant="danger" size="lg" :disabled="!allowed" data-testid="reject" @click="confirmReject = true"><AppIcon name="x" :size="16" />Reject…</AppButton>
          </template>
          <template v-else>
            <AppButton variant="primary" size="lg" :disabled="!allowed || !editChanged" :busy="mutation.isPending.value" data-testid="submit-edit" @click="sendEdit">Submit edited patch</AppButton>
            <AppButton size="lg" @click="editing = false">Discard edit</AppButton>
          </template>
        </div>
      </div>
      <p v-if="editing && !editChanged" class="text-sm text-muted">Change the diff to enable submit.</p>
    </div>

    <ConfirmDialog v-model:open="confirmApprove" title="Approve and apply this patch?" confirm-label="Approve and apply" :busy="mutation.isPending.value" description="The patch is written to the task working copy once the worker resumes. This cannot be undone from this console." @confirm="mutation.mutate({ decision: 'approve', comment: comment || undefined })">
      <p class="break-all text-xs text-muted">Approving patch <code class="rounded bg-surface-3 px-1.5 py-0.5 font-mono text-fg">{{ pending.sha256.slice(0, 16) }}…</code></p>
      <p v-if="!evidenceOk" class="mt-2 rounded-xl bg-warning-bg px-3 py-2 text-sm text-warning">Sandbox evidence is incomplete or failing. Approve only if you have verified the change another way.</p>
    </ConfirmDialog>

    <ConfirmDialog v-model:open="confirmReject" title="Reject this patch?" variant="danger" confirm-label="Reject patch" :busy="mutation.isPending.value" description="Nothing is applied. The decision and your comment are recorded." @confirm="mutation.mutate({ decision: 'reject', comment: comment || undefined })" />

    <ConfirmDialog v-model:open="stale" title="This patch is out of date" confirm-label="Refetch latest patch" hide-cancel description="The task changed while you were reviewing, so your decision was not recorded. Refetch to see the current patch before deciding again." @confirm="doRefetch">
      <p class="break-words rounded-xl bg-warning-bg px-3 py-2 text-sm text-warning" data-testid="stale-detail">Server said: {{ staleDetail }}</p>
    </ConfirmDialog>
  </section>
</template>
