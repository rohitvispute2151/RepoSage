import { describe, expect, it } from 'vitest'
import { answerState, citationHref, citationLabel, unwrapAnswer } from '@/lib/citations'

const c = { path: 'src/pkg/http.py', start_line: 38, end_line: 44, symbol: 'pkg.http.f' }

describe('citations', () => {
  it('labels single lines and ranges', () => {
    expect(citationLabel(c)).toBe('src/pkg/http.py:38-44')
    expect(citationLabel({ ...c, end_line: 38 })).toBe('src/pkg/http.py:38')
  })
  it('builds an https link and encodes path segments', () => {
    expect(citationHref({ ...c, path: 'a b/<x>.py' }, 'https://git.example/blob/main/{path}#L{start}-L{end}')).toBe('https://git.example/blob/main/a%20b/%3Cx%3E.py#L38-L44')
  })
  it('returns no link without a template or with a non-http scheme', () => {
    expect(citationHref(c, '')).toBeNull()
    expect(citationHref(c, 'javascript:alert({path})')).toBeNull()
    expect(citationHref(c, '{path}')).toBeNull()
  })
  it('never lets a hostile path change the URL scheme', () => {
    expect(citationHref({ ...c, path: 'javascript:alert(1)' }, 'https://h/{path}')).toBe('https://h/javascript%3Aalert(1)')
  })
  it('classifies found, not-found and uncited answers', () => {
    expect(answerState({ outcome: 'answered', answer: 'x', citations: [c] })).toBe('found')
    expect(answerState({ outcome: 'answered', answer: 'x', citations: [] })).toBe('uncited')
    expect(answerState({ outcome: 'answered', answer: 'x', citations: [c], found: false })).toBe('not-found')
    expect(answerState({ outcome: 'answered', answer: 'Unable to locate answer.', citations: [] })).toBe('not-found')
    expect(answerState({ outcome: 'answered', answer: '', citations: [] })).toBe('not-found')
  })

  it('unwraps a fenced JSON reply that an older backend stored as the answer', () => {
    const raw = '```json\n{\n "answer": "No info on that commit.",\n "citations": [],\n "found": false\n}\n```'
    expect(unwrapAnswer(raw)).toEqual({ answer: 'No info on that commit.', found: false })
    expect(answerState({ outcome: 'answered', answer: raw, citations: [c] })).toBe('not-found')
  })

  it('leaves ordinary answers, and JSON without an answer string, untouched', () => {
    expect(unwrapAnswer('It lives in compute_backoff.')).toEqual({ answer: 'It lives in compute_backoff.', found: undefined })
    expect(unwrapAnswer('{"x": 1}').answer).toBe('{"x": 1}')
    expect(unwrapAnswer(null)).toEqual({ answer: null, found: undefined })
  })
})
