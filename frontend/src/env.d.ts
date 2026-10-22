/// <reference types="vite/client" />
interface ImportMetaEnv {
  readonly VITE_API_BASE?: string
  /** API key sent until the user sets one. Dev builds default to the backend's dev key. */
  readonly VITE_DEFAULT_API_KEY?: string
  /** Optional https template for linking citations, e.g. https://github.com/o/r/blob/<sha>/{path}#L{start}-L{end} */
  readonly VITE_SOURCE_URL_TEMPLATE?: string
}
declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<object, object, unknown>
  export default component
}
