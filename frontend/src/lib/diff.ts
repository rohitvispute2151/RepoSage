/** Unified-diff parsing for display only. Output is plain data; components render it as text nodes. */

export type DiffLineKind = 'add' | 'del' | 'ctx' | 'hunk' | 'meta'

export interface DiffLine {
  kind: DiffLineKind
  text: string
  oldNo: number | null
  newNo: number | null
}

export interface DiffFile {
  path: string
  added: number
  removed: number
  lines: DiffLine[]
}

const HUNK = /^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@/

export function parseUnifiedDiff(diff: string): DiffFile[] {
  const files: DiffFile[] = []
  let o = 0
  let n = 0
  // Lines left in the current hunk. While > 0, a line starting with '--- ' is a removed line, not a file header.
  let remOld = 0
  let remNew = 0
  const open = (path: string): DiffFile => {
    const f: DiffFile = { path, added: 0, removed: 0, lines: [] }
    files.push(f)
    return f
  }

  for (const raw of diff.replace(/\r\n/g, '\n').split('\n')) {
    const meta = (f: DiffFile) => f.lines.push({ kind: 'meta', text: raw, oldNo: null, newNo: null })
    let cur = files[files.length - 1]
    // Content lines always carry a ' ', '+' or '-' prefix, so only '--- '/'+++ ' can be confused with headers.
    if (raw.startsWith('diff --git ')) {
      remOld = remNew = 0
      const m = /^diff --git a\/(.+?) b\/(.+)$/.exec(raw)
      meta(open(m?.[2] ?? raw.slice(11)))
      continue
    }
    if (remOld === 0 && remNew === 0 && (raw.startsWith('--- ') || raw.startsWith('+++ '))) {
      if (!cur) cur = open(raw.slice(4).replace(/^[ab]\//, ''))
      else if (raw.startsWith('+++ ') && !raw.includes('/dev/null')) cur.path = raw.slice(4).replace(/^b\//, '')
      meta(cur)
      continue
    }
    const h = HUNK.exec(raw)
    if (h) {
      cur ??= open('(patch)')
      o = Number(h[1])
      n = Number(h[3])
      remOld = h[2] === undefined ? 1 : Number(h[2])
      remNew = h[4] === undefined ? 1 : Number(h[4])
      cur.lines.push({ kind: 'hunk', text: raw, oldNo: null, newNo: null })
      continue
    }
    if (!cur) continue
    if (raw.startsWith('+')) { remNew--; cur.added++; cur.lines.push({ kind: 'add', text: raw.slice(1), oldNo: null, newNo: n++ }) }
    else if (raw.startsWith('-')) { remOld--; cur.removed++; cur.lines.push({ kind: 'del', text: raw.slice(1), oldNo: o++, newNo: null }) }
    else if (raw.startsWith(' ')) { remOld--; remNew--; cur.lines.push({ kind: 'ctx', text: raw.slice(1), oldNo: o++, newNo: n++ }) }
    else if (raw.startsWith('\\')) meta(cur)
  }
  return files
}
