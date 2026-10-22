<script setup lang="ts">
withDefaults(defineProps<{ size?: number }>(), { size: 34 })
</script>

<template>
  <svg data-app-svg :width="size" :height="size" viewBox="0 0 40 40" fill="none" aria-hidden="true" focusable="false" class="shrink-0">
    <defs>
      <linearGradient id="bm-g" x1="4" y1="2" x2="38" y2="40" gradientUnits="userSpaceOnUse">
        <stop offset="0" stop-color="var(--accent)" />
        <stop offset="1" stop-color="color-mix(in srgb, var(--accent) 55%, #5b7cff)" />
      </linearGradient>
    </defs>
    <rect width="40" height="40" rx="11" fill="url(#bm-g)" />
    <!-- a trunk with a verified branch: the agent proposes, the human merges -->
    <path d="M14 10v20M14 20c0-5 12-3 12-9" stroke="var(--accent-fg)" stroke-width="2.4" stroke-linecap="round" />
    <circle cx="14" cy="10" r="3" fill="var(--accent-fg)" />
    <circle cx="14" cy="30" r="3" fill="var(--accent-fg)" />
    <circle cx="26" cy="11" r="3" fill="var(--accent-fg)" />
    <path d="m24.4 11 1.2 1.2 2.2-2.4" stroke="var(--accent)" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" />
  </svg>
</template>
