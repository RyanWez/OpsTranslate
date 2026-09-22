import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '../api'
import type { UsageLogItem } from '../types'

export const useLogsStore = defineStore('logs', () => {
  const logs = ref<UsageLogItem[]>([])
  const loading = ref<boolean>(false)
  const limit = ref<number>(100)
  let liveSyncTimer: any = null

  async function fetchLogs(silent = false): Promise<void> {
    if (!silent) {
      loading.value = true
    }
    try {
      const res = await api.getLogs(limit.value)
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

  return {
    logs,
    loading,
    limit,
    fetchLogs,
    startLiveSync,
    stopLiveSync,
  }
})
