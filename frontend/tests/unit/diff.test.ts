import { describe, expect, it } from 'vitest'
import { parseUnifiedDiff } from '@/lib/diff'
import { PATCH_V1 } from '@mock/backend'

describe('parseUnifiedDiff', () => {
  it('parses files, counts and line numbers', () => {
    const [f] = parseUnifiedDiff(PATCH_V1)
    expect(f?.path).toBe('src/pkg/http.py')
    expect(f).toMatchObject({ added: 1, removed: 1 })
    expect(f?.lines.find((l) => l.kind === 'add')).toMatchObject({ newNo: 42, text: '    return base * 2 ** attempt' })
    expect(f?.lines.find((l) => l.kind === 'del')).toMatchObject({ oldNo: 42 })
  })

  it('keeps hostile markup as plain text', () => {
    const [f] = parseUnifiedDiff(PATCH_V1)
    expect(f?.lines.some((l) => l.text.includes('<img src=x onerror='))).toBe(true)
  })

  it('does not mistake a removed line starting with "-- " for a file header', () => {
    const diff = 'diff --git a/a.sql b/a.sql\n--- a/a.sql\n+++ b/a.sql\n@@ -1,2 +1,1 @@\n--- old comment\n keep\n'
    const files = parseUnifiedDiff(diff)
    expect(files).toHaveLength(1)
    expect(files[0]).toMatchObject({ removed: 1, added: 0 })
  })

  it('handles multiple files and empty input', () => {
    const two = PATCH_V1 + PATCH_V1.replaceAll('http.py', 'util.py')
    expect(parseUnifiedDiff(two).map((f) => f.path)).toEqual(['src/pkg/http.py', 'src/pkg/util.py'])
    expect(parseUnifiedDiff('')).toEqual([])
  })
})
