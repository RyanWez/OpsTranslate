import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '../api'
import { useRealtimeStore } from './realtime'
import type { ProviderItem, ProviderPayload, TestProviderResult } from '../types'

export const useProvidersStore = defineStore('providers', () => {
  const providers = ref<ProviderItem[]>([])
  const loading = ref<boolean>(false)
  const testing = ref<boolean>(false)
  const testResult = ref<TestProviderResult | null>(null)
  let liveSyncTimer: any = null

  async function fetchProviders(silent = false): Promise<void> {
    if (!silent) {
      loading.value = true
    }
    try {
      const res = await api.getProviders()
      providers.value = res.data.providers || []
    } finally {
      if (!silent) {
        loading.value = false
      }
    }
  }

  function startLiveSync(intervalMs = 3000): void {
    stopLiveSync()
    fetchProviders()
    liveSyncTimer = setInterval(() => {
      if (document.visibilityState !== 'hidden') {
        const realtimeStore = useRealtimeStore()
        if (!realtimeStore.isConnected) {
          fetchProviders(true)
        }
      }
    }, intervalMs)
  }

  function stopLiveSync(): void {
    if (liveSyncTimer) {
      clearInterval(liveSyncTimer)
      liveSyncTimer = null
    }
  }

  async function saveProvider(id: number | string | null, payload: ProviderPayload): Promise<boolean> {
    loading.value = true
    try {
      if (id !== null) {
        await api.updateProvider(id, payload)
      } else {
        await api.createProvider(payload)
      }
      await fetchProviders()
      return true
    } finally {
      loading.value = false
    }
  }

  async function deleteProvider(id: number | string): Promise<boolean> {
    loading.value = true
    try {
      await api.deleteProvider(id)
      await fetchProviders()
      return true
    } finally {
      loading.value = false
    }
  }

  async function testProviderConnection(payload: {
    id?: number | string
    base_url: string
    api_key?: string
    model: string
    timeout_s?: number
  }): Promise<TestProviderResult> {

    testing.value = true
    testResult.value = null
    try {
      const res = await api.testProvider(payload)
      testResult.value = res.data
      return res.data
    } catch (err: any) {
      const fallback = {
        ok: false,
        status_code: 0,
        latency_ms: 0,
        error: err.response?.data?.detail || err.message,
      }
      testResult.value = fallback
      return fallback
    } finally {
      testing.value = false
    }
  }

  return {
    providers,
    loading,
    testing,
    testResult,
    fetchProviders,
    startLiveSync,
    stopLiveSync,
    saveProvider,
    deleteProvider,
    testProviderConnection,
  }
})
