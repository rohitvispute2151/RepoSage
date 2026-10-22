<script setup lang="ts">
import { computed } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import { fetchHealth } from '@/api/health'
import { useSessionStore } from '@/stores/session'
import AppIcon, { type IconName } from './AppIcon.vue'
import BrandMark from './BrandMark.vue'

const session = useSessionStore()
const themeLabel = computed(() => ({ system: 'System theme', light: 'Light theme', dark: 'Dark theme' })[session.theme])
const themeIcon = computed<IconName>(() => ({ system: 'monitor', light: 'sun', dark: 'moon' } as const)[session.theme])

// Same key as the overview page, so this shares one request instead of adding another.
const live = useQuery({ queryKey: ['healthz'], queryFn: fetchHealth, refetchInterval: 15000, retry: false })
const api = computed(() => (live.isError.value ? 'offline' : live.isPending.value ? 'checking' : 'online'))

const links: { to: string; label: string; icon: IconName; exact?: boolean }[] = [
  { to: '/', label: 'Home', icon: 'home', exact: true },
  { to: '/repos', label: 'Repositories', icon: 'repo' },
  { to: '/tasks/new', label: 'New task', icon: 'plus' },
  { to: '/evals/compare', label: 'Eval compare', icon: 'chart' },
]
</script>

<template>
  <header class="z-30 border-b border-line bg-bg/80 backdrop-blur-xl lg:sticky lg:top-0 lg:flex lg:h-screen lg:flex-col lg:border-b-0 lg:border-r">
    <div class="flex items-center gap-3 px-4 py-3 lg:px-5 lg:py-6">
      <RouterLink to="/" class="flex items-center gap-3 rounded-lg">
        <BrandMark />
        <span class="leading-tight">
          <span class="block text-[0.95rem] font-semibold tracking-tight">RepoSage</span>
          <span class="eyebrow block !text-[0.62rem]">Console</span>
        </span>
      </RouterLink>
      <button
        type="button"
        class="ml-auto inline-flex items-center gap-2 rounded-[10px] border border-line px-2.5 py-1.5 text-xs text-muted transition hover:border-line-strong hover:bg-surface-2 hover:text-fg lg:hidden"
        :aria-label="`${themeLabel}. Activate to change.`"
        @click="session.cycleTheme()"
      >
        <AppIcon :name="themeIcon" :size="15" />{{ themeLabel }}
      </button>
    </div>

    <nav aria-label="Primary" class="scroll-thin flex gap-1 overflow-x-auto px-3 pb-2 lg:flex-1 lg:flex-col lg:overflow-visible lg:px-3 lg:pb-0">
      <RouterLink
        v-for="l in links"
        :key="l.to"
        :to="l.to"
        class="nav-link"
        :active-class="l.exact ? '' : 'is-active'"
        exact-active-class="is-active"
      >
        <AppIcon :name="l.icon" :size="17" />{{ l.label }}
      </RouterLink>
    </nav>

    <div class="hidden space-y-3 border-t border-line p-4 lg:block">
      <p class="flex items-center gap-2 text-xs text-muted" data-testid="rail-api-status">
        <span
          class="live-dot"
          :class="api === 'online' ? 'text-success' : api === 'offline' ? 'still text-danger' : 'still text-muted'"
        />
        <span>API {{ api }}</span>
      </p>
      <button
        type="button"
        class="flex w-full items-center gap-2.5 rounded-[10px] border border-line px-3 py-2 text-sm text-muted transition hover:border-line-strong hover:bg-surface-2 hover:text-fg"
        :aria-label="`${themeLabel}. Activate to change.`"
        @click="session.cycleTheme()"
      >
        <AppIcon :name="themeIcon" :size="16" />{{ themeLabel }}
      </button>
    </div>
  </header>
</template>

<style scoped>
.nav-link {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 0.65rem;
  white-space: nowrap;
  border-radius: 10px;
  padding: 0.55rem 0.8rem;
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--muted);
  transition: background 0.15s, color 0.15s;
}
.nav-link:hover { background: var(--surface-2); color: var(--fg); }
.nav-link.is-active { background: var(--surface-3); color: var(--fg); }
.nav-link.is-active svg { color: var(--accent); }
@media (min-width: 1024px) {
  .nav-link.is-active::before {
    content: '';
    position: absolute;
    left: -0.75rem;
    top: 22%;
    bottom: 22%;
    width: 3px;
    border-radius: 0 3px 3px 0;
    background: var(--accent);
    box-shadow: 0 0 12px var(--accent);
  }
}
</style>
