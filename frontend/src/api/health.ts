import { api, unwrap } from './client'

export const fetchHealth = () => unwrap(api.GET('/healthz'))
export const fetchReadiness = () => unwrap(api.GET('/readyz'))
