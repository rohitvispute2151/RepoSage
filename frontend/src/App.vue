<script setup lang="ts">
import AppHeader from '@/components/AppHeader.vue'
</script>

<template>
  <a class="skip-link" href="#main">Skip to content</a>
  <div class="min-h-screen lg:grid lg:grid-cols-[16.5rem_minmax(0,1fr)]">
    <AppHeader />
    <main id="main" tabindex="-1" class="mx-auto w-full max-w-6xl px-4 py-8 outline-none sm:px-8 lg:py-10">
      <RouterView />
    </main>
  </div>
</template>
