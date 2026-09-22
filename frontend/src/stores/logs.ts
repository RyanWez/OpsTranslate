import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '../api'
import type { UsageLogItem } from '../types'

export const useLogsStore = defineStore('logs', () => {
  const logs = ref<UsageLogItem[]>([])
  const loading = ref<boolean>(false)
  const limit = ref<number>(100)
  const dateRange = ref<[number, number] | null>(null)
  const selectedProvider = ref<string | null>(null)
  let liveSyncTimer: any = null

  async function fetchLogs(silent = false): Promise<void> {
    if (!silent) {
      loading.value = true
    }
    try {
      const params: Record<string, any> = { limit: limit.value }
      if (dateRange.value && dateRange.value.length === 2) {
        params.start_time = dateRange.value[0]
        params.end_time = dateRange.value[1]
      }
      if (selectedProvider.value && selectedProvider.value !== 'all') {
        params.provider = selectedProvider.value
      }
      const res = await api.getLogs(params)
      logs.value = res.data.logs || []
    } finally {
      if (!silent) {
        loading.value = false
      }
    }
  }

  function startLiveSync(intervalMs = 3000): void {
    stopLiveSync()
    fetchLogs()
    liveSyncTimer = setInterval(() => {
      if (document.visibilityState !== 'hidden') {
        fetchLogs(true)
      }
    }, intervalMs)
  }

  function stopLiveSync(): void {
    if (liveSyncTimer) {
      clearInterval(liveSyncTimer)
      liveSyncTimer = null
    }
  }

  function addLiveLog(item: UsageLogItem): void {
    if (!logs.value.some((l) => l.id === item.id)) {
      logs.value.unshift(item)
      if (logs.value.length > limit.value) {
        logs.value.pop()
      }
    }
  }

  return {
    logs,
    loading,
    limit,
    dateRange,
    selectedProvider,
    fetchLogs,
    addLiveLog,
    startLiveSync,
    stopLiveSync,
  }
})
