/**
 * Minimal single-line Python tokenizer for diff display. It returns plain segments; components render each one as a
 * text node inside a <span>, so repository content never becomes markup. Multi-line strings are not tracked: a diff
 * line is shown without context, and a wrong colour is harmless where a wrong parse of untrusted text would not be.
 */
export type TokenClass = 'kw' | 'str' | 'num' | 'com' | 'fn'
export interface Segment { text: string; cls?: TokenClass }

const KEYWORDS = new Set([
  'False', 'None', 'True', 'and', 'as', 'assert', 'async', 'await', 'break', 'class', 'continue', 'def', 'del', 'elif', 'else',
  'except', 'finally', 'for', 'from', 'global', 'if', 'import', 'in', 'is', 'lambda', 'nonlocal', 'not', 'or', 'pass', 'raise',
  'return', 'try', 'while', 'with', 'yield', 'self', 'cls',
])

const TOKEN = /(#.*$)|("""|'''|"(?:\\.|[^"\\])*"?|'(?:\\.|[^'\\])*'?)|(\b\d[\d_]*(?:\.\d+)?(?:e[+-]?\d+)?\b)|(@[A-Za-z_][\w.]*)|([A-Za-z_]\w*)/g

export function highlightPython(line: string): Segment[] {
  const out: Segment[] = []
  let last = 0
  let prevWord = ''
  for (const m of line.matchAll(TOKEN)) {
    const at = m.index ?? 0
    if (at > last) out.push({ text: line.slice(last, at) })
    const [text, com, str, num, deco, word] = m
    if (com) out.push({ text, cls: 'com' })
    else if (str) out.push({ text, cls: 'str' })
    else if (num) out.push({ text, cls: 'num' })
    else if (deco) out.push({ text, cls: 'fn' })
    else if (word) {
      if (prevWord === 'def' || prevWord === 'class') out.push({ text, cls: 'fn' })
      else if (KEYWORDS.has(word)) out.push({ text, cls: 'kw' })
      else out.push({ text })
      prevWord = word
    }
    if (!word && text.trim()) prevWord = ''
    last = at + text.length
  }
  if (last < line.length) out.push({ text: line.slice(last) })
  return out.length ? out : [{ text: line }]
}

export const isPython = (path: string) => /\.pyi?$/.test(path)
