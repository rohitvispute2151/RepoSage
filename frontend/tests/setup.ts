import { afterEach } from 'vitest'

// jsdom lacks these; Reka UI (dialogs, tabs, progress) touches them.
class RO { observe() {} unobserve() {} disconnect() {} }
globalThis.ResizeObserver ??= RO as unknown as typeof ResizeObserver
Element.prototype.scrollIntoView ??= () => {}
Element.prototype.hasPointerCapture ??= () => false
Element.prototype.releasePointerCapture ??= () => {}

// axe probes canvas for icon ligatures; jsdom has none, so answer "no context" quietly.
HTMLCanvasElement.prototype.getContext = (() => null) as unknown as HTMLCanvasElement['getContext']

afterEach(() => {
  document.body.innerHTML = ''
})
