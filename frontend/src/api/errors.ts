export type ApiErrorKind = 'auth' | 'not_found' | 'conflict' | 'validation' | 'server' | 'network' | 'contract'

export class ApiError extends Error {
  constructor(
    public readonly kind: ApiErrorKind,
    public readonly status: number | null,
    message: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }

  /** Worth retrying automatically (transient infrastructure trouble). */
  get transient(): boolean {
    return this.kind === 'server' || this.kind === 'network'
  }
}

/** FastAPI sends `{detail: string}` or `{detail: ValidationError[]}`. Always flattened to plain text. */
export function detailText(body: unknown): string {
  if (typeof body === 'object' && body !== null && 'detail' in body) {
    const d = (body as { detail: unknown }).detail
    if (typeof d === 'string') return d
    if (Array.isArray(d)) {
      return d
        .map((e) => (typeof e === 'object' && e && 'msg' in e ? String((e as { msg: unknown }).msg) : String(e)))
        .join('; ')
    }
  }
  return ''
}

export function errorFromStatus(status: number, body: unknown): ApiError {
  const detail = detailText(body)
  if (status === 401 || status === 403) return new ApiError('auth', status, detail || 'API key missing or rejected')
  if (status === 404) return new ApiError('not_found', status, detail || 'Not found')
  if (status === 409) return new ApiError('conflict', status, detail || 'Conflict')
  if (status === 422 || status === 400) return new ApiError('validation', status, detail || 'Request rejected')
  return new ApiError('server', status, detail || `Server error (${status})`)
}

export function networkError(cause: unknown): ApiError {
  return new ApiError('network', null, cause instanceof Error ? cause.message : 'Network unreachable')
}
