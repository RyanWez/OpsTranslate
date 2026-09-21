import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '../api'
import type { PolicyData } from '../types'

export const usePolicyStore = defineStore('policy', () => {
  const policy = ref<PolicyData | null>(null)
  const loading = ref<boolean>(false)
  const error = ref<string | null>(null)

  async function fetchPolicy(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const res = await api.getPolicy()
      policy.value = res.data
    } catch (err: any) {
      error.value = err.message || 'Failed to load policy data'
    } finally {
      loading.value = false
    }
  }

  return {
    policy,
    loading,
    error,
    fetchPolicy,
  }
})
