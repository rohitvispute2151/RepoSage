import { QueryClient } from '@tanstack/vue-query'
import { ApiError } from './errors'

/** Retry only transient infrastructure failures (5xx, network), twice. Auth, 404 and contract errors fail fast. */
export const shouldRetry = (count: number, err: unknown) => err instanceof ApiError && err.transient && count < 2

export const createQueryClient = () => new QueryClient({ defaultOptions: { queries: { retry: shouldRetry, refetchOnWindowFocus: false } } })
