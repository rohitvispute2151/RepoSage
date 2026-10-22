<script setup lang="ts">
withDefaults(defineProps<{ variant?: 'primary' | 'secondary' | 'danger' | 'ghost'; type?: 'button' | 'submit'; disabled?: boolean; busy?: boolean; size?: 'md' | 'lg' }>(), {
  variant: 'secondary',
  type: 'button',
  disabled: false,
  busy: false,
  size: 'md',
})
</script>

<template>
  <button
    :type="type"
    :disabled="disabled || busy"
    :aria-busy="busy || undefined"
    class="group relative inline-flex items-center justify-center gap-2 rounded-[10px] border font-medium transition duration-150 active:translate-y-px disabled:cursor-not-allowed disabled:opacity-45 disabled:active:translate-y-0"
    :class="[
      size === 'lg' ? 'px-5 py-3 text-sm' : 'px-3.5 py-2 text-sm',
      {
        'border-transparent bg-accent text-accent-fg shadow-[0_6px_20px_-8px_var(--accent)] hover:brightness-110 disabled:shadow-none': variant === 'primary',
        'border-line-strong bg-surface-2 text-fg hover:border-accent/50 hover:bg-surface-3': variant === 'secondary',
        'border-danger/35 bg-danger-bg text-danger hover:border-danger/70 hover:brightness-110': variant === 'danger',
        'border-transparent bg-transparent text-muted hover:bg-surface-2 hover:text-fg': variant === 'ghost',
      },
    ]"
  >
    <span v-if="busy" aria-hidden="true" class="size-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
    <slot />
  </button>
</template>
