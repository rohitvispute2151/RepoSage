import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

export type ThemePref = 'system' | 'light' | 'dark'

const read = (k: string): string | null => {
  try { return globalThis.localStorage?.getItem(k) ?? null } catch { return null }
}
const write = (k: string, v: string) => {
  try { globalThis.localStorage?.setItem(k, v) } catch { /* storage unavailable: keep in memory */ }
}

/**
 * Key used until the user sets one. VITE_DEFAULT_API_KEY wins; in dev builds it falls back to the backend's own
 * default (`reposage-dev-key`, src/reposage/config.py). Production builds get no baked-in key.
 */
const DEFAULT_KEY: string = import.meta.env.VITE_DEFAULT_API_KEY ?? (import.meta.env.DEV ? 'reposage-dev-key' : '')

export const useSessionStore = defineStore('session', () => {
  const apiKey = ref(read('reposage.apiKey') ?? DEFAULT_KEY)
  const theme = ref<ThemePref>((read('reposage.theme') as ThemePref | null) ?? 'system')

  watch(apiKey, (v) => write('reposage.apiKey', v))
  watch(theme, (v) => write('reposage.theme', v))

  function applyTheme() {
    const root = globalThis.document?.documentElement
    if (!root) return
    if (theme.value === 'system') root.removeAttribute('data-theme')
    else root.setAttribute('data-theme', theme.value)
  }
  watch(theme, applyTheme, { immediate: true })

  function cycleTheme() {
    theme.value = theme.value === 'system' ? 'light' : theme.value === 'light' ? 'dark' : 'system'
  }

  return { apiKey, theme, cycleTheme }
})
