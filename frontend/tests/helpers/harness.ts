import { createPinia, setActivePinia } from 'pinia'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { http } from 'msw'
import { setupServer } from 'msw/node'
import { MockBackend, DEV_KEY } from '@mock/backend'
import { handle } from '@mock/http'
import App from '@/App.vue'
import { routes } from '@/router'
import { useSessionStore } from '@/stores/session'
import { useTrajectoryStore } from '@/stores/trajectory'

export const API = 'http://api.test'
export const backend = new MockBackend({ stepDelayMs: 0 })
export const mockHandler = http.all(`${API}/*`, ({ request }) => handle(request, backend, 10))
export const server = setupServer(mockHandler)

const mounted: Array<() => void> = []
export function unmountAll() {
  while (mounted.length) mounted.pop()!()
}

export async function mountApp(path: string, opts: { apiKey?: string } = {}) {
  const pinia = createPinia()
  setActivePinia(pinia)
  useSessionStore().apiKey = opts.apiKey ?? DEV_KEY
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const router = createRouter({ history: createMemoryHistory(), routes })
  await router.push(path)
  await router.isReady()
  const wrapper = mount(App, { attachTo: document.body, global: { plugins: [pinia, [VueQueryPlugin, { queryClient }], router] } })
  mounted.push(() => {
    useTrajectoryStore(pinia).stop()
    wrapper.unmount()
    queryClient.clear()
  })
  return { wrapper, router, queryClient, pinia }
}

export const text = () => document.body.textContent ?? ''
export const byTestId = (id: string) => document.body.querySelector<HTMLElement>(`[data-testid="${id}"]`)
export const clickTestId = (id: string) => {
  const el = byTestId(id)
  if (!el) throw new Error(`no element with data-testid=${id}`)
  el.click()
}
export const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))
