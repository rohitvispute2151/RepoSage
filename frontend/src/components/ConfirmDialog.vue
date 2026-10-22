<script setup lang="ts">
import { DialogContent, DialogDescription, DialogOverlay, DialogPortal, DialogRoot, DialogTitle } from 'reka-ui'
import AppButton from './AppButton.vue'
import AppIcon from './AppIcon.vue'

withDefaults(defineProps<{ title: string; description: string; confirmLabel: string; variant?: 'primary' | 'danger'; busy?: boolean; hideCancel?: boolean; confirmDisabled?: boolean }>(), {
  variant: 'primary',
  busy: false,
  hideCancel: false,
  confirmDisabled: false,
})
const open = defineModel<boolean>('open', { required: true })
defineEmits<{ confirm: [] }>()
</script>

<template>
  <DialogRoot v-model:open="open">
    <DialogPortal>
      <DialogOverlay class="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm" />
      <DialogContent class="card fixed left-1/2 top-1/2 z-50 w-[min(34rem,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 p-6 text-fg !shadow-[var(--shadow-pop)]">
        <div class="flex gap-4">
          <span class="grid size-10 shrink-0 place-items-center rounded-xl" :class="variant === 'danger' ? 'bg-danger-bg text-danger' : 'bg-accent-soft text-accent'">
            <AppIcon :name="variant === 'danger' ? 'alert' : 'shield'" :size="20" />
          </span>
          <div class="min-w-0 flex-1">
            <DialogTitle class="text-base font-semibold tracking-tight">{{ title }}</DialogTitle>
            <DialogDescription class="mt-1 text-sm leading-6 text-muted">{{ description }}</DialogDescription>
            <div class="mt-3"><slot /></div>
          </div>
        </div>
        <div class="mt-6 flex justify-end gap-2">
          <AppButton v-if="!hideCancel" variant="secondary" :disabled="busy" @click="open = false">Cancel</AppButton>
          <AppButton :variant="variant" :busy="busy" :disabled="confirmDisabled" data-testid="dialog-confirm" @click="$emit('confirm')">{{ confirmLabel }}</AppButton>
        </div>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>
