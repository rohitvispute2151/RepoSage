import { computed, type Ref } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import { fetchTask } from '@/api/tasks'
import { STATUS_META } from '@/lib/statusMeta'

export function useTask(taskId: Ref<string>) {
  return useQuery({
    queryKey: computed(() => ['task', taskId.value]),
    queryFn: () => fetchTask(taskId.value),
    // Polling is the source of truth for status; SSE adds detail. Stops once terminal.
    refetchInterval: (q) => {
      const s = q.state.data?.status
      return s && s !== 'unknown' && STATUS_META[s].terminal ? false : 2000
    },
    staleTime: 0,
  })
}
