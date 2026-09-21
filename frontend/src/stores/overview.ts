import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '../api'
import type { OverviewStats } from '../types'

export const useOverviewStore = defineStore('overview', () => {
  const stats = ref<OverviewStats | null>(null)
  const loading = ref<boolean>(false)
  const error = ref<string | null>(null)
  let timer: any = null

  async function fetchOverview(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const res = await api.getOverview()
      stats.value = res.data
    } catch (err: any) {
      error.value = err.message || 'Failed to load system overview'
    } finally {
      loading.value = false
    }
  }

  function startAutoRefresh(intervalMs = 15000): void {
    stopAutoRefresh()
    fetchOverview()
    timer = setInterval(fetchOverview, intervalMs)
  }

  function stopAutoRefresh(): void {
    if (timer) {
      clearInterval(timer)
      timer = null
    }
  }

  return {
    stats,
    loading,
    error,
    fetchOverview,
    startAutoRefresh,
    stopAutoRefresh,
  }
})
