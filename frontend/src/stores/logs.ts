import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '../api'
import type { UsageLogItem } from '../types'

export const useLogsStore = defineStore('logs', () => {
  const logs = ref<UsageLogItem[]>([])
  const loading = ref<boolean>(false)
  const limit = ref<number>(100)

  async function fetchLogs(): Promise<void> {
    loading.value = true
    try {
      const res = await api.getLogs(limit.value)
      logs.value = res.data.logs || []
    } finally {
      loading.value = false
    }
  }

  return {
    logs,
    loading,
    limit,
    fetchLogs,
  }
})
