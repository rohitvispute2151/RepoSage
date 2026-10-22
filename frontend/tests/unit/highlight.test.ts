import { describe, expect, it } from 'vitest'
import { highlightPython, isPython } from '@/lib/highlight'

const join = (s: { text: string }[]) => s.map((x) => x.text).join('')

describe('highlightPython', () => {
  it('never loses or reorders characters', () => {
    for (const line of ['    return base * 2 ** attempt', 'def f(x: int = 3) -> str:  # note', `s = "a\\"b" + 'c`, '@app.route("/x")', '', '   ']) {
      expect(join(highlightPython(line))).toBe(line)
    }
  })

  it('classifies keywords, strings, numbers, comments and definitions', () => {
    const segs = highlightPython('def compute(attempt, base=0.5):  # retry')
    const by = (cls: string) => segs.filter((s) => s.cls === cls).map((s) => s.text)
    expect(by('kw')).toEqual(['def'])
    expect(by('fn')).toEqual(['compute'])
    expect(by('num')).toEqual(['0.5'])
    expect(by('com')).toEqual(['# retry'])
    expect(highlightPython('x = "hi"').find((s) => s.cls === 'str')?.text).toBe('"hi"')
  })

  it('treats hostile text as inert data', () => {
    const hostile = '<img src=x onerror="window.__pwned=1">  # </script>'
    expect(join(highlightPython(hostile))).toBe(hostile)
  })

  it('only highlights python paths', () => {
    expect(isPython('src/pkg/http.py')).toBe(true)
    expect(isPython('README.md')).toBe(false)
  })
})
