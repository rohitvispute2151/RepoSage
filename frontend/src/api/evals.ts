import { ApiError } from './errors'
import { API_BASE } from './client'
import { EvalRunExportSchema, type EvalRunExport } from './contracts'
import { useSessionStore } from '@/stores/session'
import { errorFromStatus, networkError } from './errors'

/** Not part of the generated OpenAPI client: the backend exposes no eval endpoint yet (see docs/BACKEND_CONTRACT.md). */
export async function fetchEvalRun(runId: string): Promise<EvalRunExport> {
  let res: Response
  try {
    res = await fetch(`${API_BASE}/v1/evals/runs/${encodeURIComponent(runId)}`, {
      headers: { 'X-API-Key': useSessionStore().apiKey },
    })
  } catch (e) {
    throw networkError(e)
  }
  if (!res.ok) throw errorFromStatus(res.status, await res.json().catch(() => null))
  return parseEvalRun(await res.json().catch(() => null))
}

export function parseEvalRun(json: unknown): EvalRunExport {
  const p = EvalRunExportSchema.safeParse(json)
  if (!p.success) {
    const i = p.error.issues[0]
    throw new ApiError('contract', null, `Not a valid eval run export (${i?.path.join('.') || 'root'}: ${i?.message ?? 'invalid'})`)
  }
  return p.data
}
