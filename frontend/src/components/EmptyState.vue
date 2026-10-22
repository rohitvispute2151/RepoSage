<script setup lang="ts">
import AppIcon from './AppIcon.vue'
defineProps<{ title: string }>()
</script>

<template>
  <div class="rounded-2xl border border-dashed border-line-strong bg-surface/60 px-6 py-10 text-center" data-testid="empty-state">
    <span class="mx-auto mb-3 grid size-10 place-items-center rounded-xl bg-surface-3 text-muted"><AppIcon name="inbox" :size="20" /></span>
    <p class="font-medium text-fg">{{ title }}</p>
    <p v-if="$slots.default" class="mx-auto mt-1.5 max-w-prose text-sm leading-6 text-muted"><slot /></p>
  </div>
</template>
