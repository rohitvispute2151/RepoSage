import { api, unwrap } from './client'
import type { components } from './schema'

export type RepoCreate = components['schemas']['RepoCreate']
export type RepoListItem = components['schemas']['RepoListItem']
export type Snapshot = components['schemas']['RepoSnapshotResponse']

export const SNAPSHOT_FINAL = ['ready', 'failed'] as const
export const isSnapshotFinal = (s: string) => (SNAPSHOT_FINAL as readonly string[]).includes(s)

export const registerRepo = (body: RepoCreate) => unwrap(api.POST('/v1/repos', { body }))
export const fetchSnapshot = (id: string) => unwrap(api.GET('/v1/repos/{snapshot_id}', { params: { path: { snapshot_id: id } } }))
export const listRepos = (query: { limit?: number; offset?: number; status?: 'queued' | 'ingesting' | 'ready' | 'failed' } = {}) => unwrap(api.GET('/v1/repos', { params: { query } }))
