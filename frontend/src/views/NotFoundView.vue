<script setup lang="ts">
import AppIcon from '@/components/AppIcon.vue'
</script>

<template>
  <div class="mx-auto max-w-md py-16 text-center">
    <p class="font-mono text-6xl font-semibold tracking-tight text-accent">404</p>
    <h1 class="mt-4 text-xl font-semibold">Page not found</h1>
    <p class="mt-2 text-sm text-muted">That route does not exist in this console.</p>
    <RouterLink to="/" class="link mt-6 inline-flex items-center gap-2 text-sm font-medium">Back to start<AppIcon name="arrow" :size="15" /></RouterLink>
  </div>
</template>
