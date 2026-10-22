import type { Citation } from '@/api/contracts'

export const citationLabel = (c: Citation) =>
  c.start_line === c.end_line ? `${c.path}:${c.start_line}` : `${c.path}:${c.start_line}-${c.end_line}`

/**
 * Builds an external link from VITE_SOURCE_URL_TEMPLATE ({path},{start},{end}). Only http(s) URLs are returned,
 * and every substituted value is percent-encoded, so model-supplied paths can never produce a javascript: URL.
 */
export function citationHref(c: Citation, template: string | undefined = import.meta.env.VITE_SOURCE_URL_TEMPLATE): string | null {
  if (!template) return null
  const encodedPath = c.path.split('/').map(encodeURIComponent).join('/')
  const url = template
    .replaceAll('{path}', encodedPath)
    .replaceAll('{start}', String(c.start_line))
    .replaceAll('{end}', String(c.end_line))
  try {
    const u = new URL(url)
    return u.protocol === 'https:' || u.protocol === 'http:' ? u.toString() : null
  } catch {
    return null
  }
}

/**
 * Older results stored the model's raw reply, often a ```json fenced object, as the answer. Pull the real answer (and
 * `found`) back out. Anything that is not such an object is returned untouched. Output stays plain text.
 */
export function unwrapAnswer(answer: string | null | undefined, found?: boolean): { answer: string | null; found: boolean | undefined } {
  const raw = answer ?? null
  if (!raw) return { answer: raw, found }
  const fenced = /```(?:json)?\s*([\s\S]*?)```/i.exec(raw)?.[1]
  const braces = raw.indexOf('{') >= 0 && raw.lastIndexOf('}') > raw.indexOf('{') ? raw.slice(raw.indexOf('{'), raw.lastIndexOf('}') + 1) : undefined
  for (const c of [raw.trim(), fenced?.trim(), braces]) {
    if (!c) continue
    try {
      const o: unknown = JSON.parse(c)
      if (o && typeof o === 'object' && !Array.isArray(o) && typeof (o as { answer?: unknown }).answer === 'string') {
        const inner = o as { answer: string; found?: unknown }
        return { answer: inner.answer, found: found ?? (typeof inner.found === 'boolean' ? inner.found : undefined) }
      }
    } catch { /* not JSON: try the next candidate */ }
  }
  return { answer: raw, found }
}

/** The backend never sends `found`; infer "nothing found" from the data we do get. */
export function answerState(r: { found?: boolean | undefined; answer?: string | null | undefined; citations: Citation[]; outcome: string }):
  | 'found'
  | 'not-found'
  | 'uncited' {
  const u = unwrapAnswer(r.answer, r.found)
  if (u.found === false) return 'not-found'
  if (!u.answer || u.answer.trim() === '' || u.answer === 'Unable to locate answer.') return 'not-found'
  if (r.citations.length === 0) return 'uncited'
  return 'found'
}
