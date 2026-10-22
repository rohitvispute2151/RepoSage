import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

export interface RecentSnapshot { id: string; name: string; commit: string; at: string }
export interface RecentTask { id: string; mode: string; label: string; at: string }

const load = <T>(k: string): T[] => {
  try { const v = JSON.parse(globalThis.localStorage?.getItem(k) ?? '[]'); return Array.isArray(v) ? v : [] } catch { return [] }
}
const save = (k: string, v: unknown) => { try { globalThis.localStorage?.setItem(k, JSON.stringify(v)) } catch { /* in-memory only */ } }

/** The API has no list endpoints, so the console remembers what this browser created or opened. */
export const useHistoryStore = defineStore('history', () => {
  const snapshots = ref<RecentSnapshot[]>(load('reposage.snapshots'))
  const tasks = ref<RecentTask[]>(load('reposage.tasks'))
  watch(snapshots, (v) => save('reposage.snapshots', v), { deep: true })
  watch(tasks, (v) => save('reposage.tasks', v), { deep: true })

  const addSnapshot = (s: Omit<RecentSnapshot, 'at'>) => {
    snapshots.value = [{ ...s, at: new Date().toISOString() }, ...snapshots.value.filter((x) => x.id !== s.id)].slice(0, 20)
  }
  const addTask = (t: Omit<RecentTask, 'at'>) => {
    tasks.value = [{ ...t, at: new Date().toISOString() }, ...tasks.value.filter((x) => x.id !== t.id)].slice(0, 30)
  }
  const clear = () => { snapshots.value = []; tasks.value = [] }
  return { snapshots, tasks, addSnapshot, addTask, clear }
})
