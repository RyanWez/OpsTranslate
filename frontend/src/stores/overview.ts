import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '../api'
import type { OverviewStats } from '../types'

export const useOverviewStore = defineStore('overview', () => {
  const stats = ref<OverviewStats | null>(null)
  const loading = ref<boolean>(false)
  const error = ref<string | null>(null)
  let timer: any = null

  async function fetchOverview(silent = false): Promise<void> {
    if (!silent) {
      loading.value = true
    }
    error.value = null
    try {
      const res = await api.getOverview()
      stats.value = res.data
    } catch (err: any) {
      if (!silent) {
        error.value = err.message || 'Failed to load system overview'
      }
    } finally {
      if (!silent) {
        loading.value = false
      }
    }
  }

  function startAutoRefresh(intervalMs = 3000): void {
    stopAutoRefresh()
    fetchOverview()
    timer = setInterval(() => {
      if (document.visibilityState !== 'hidden') {
        fetchOverview(true)
      }
    }, intervalMs)
  }

  function stopAutoRefresh(): void {
    if (timer) {
      clearInterval(timer)
      timer = null
    }
  }

  function updateTelemetry(telemetry: any): void {
    if (stats.value) {
      stats.value.telemetry = telemetry
    }
  }

  return {
    stats,
    loading,
    error,
    fetchOverview,
    updateTelemetry,
    startAutoRefresh,
    stopAutoRefresh,
  }
})
