import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '../api'
import type { PlaygroundResult } from '../types'

export const usePlaygroundStore = defineStore('playground', () => {
  const inputText = ref<string>('မင်္ဂလာပါ ဂိမ်းအိုင်ဒီ မှားနေပါတယ် https://x.co/ops 0912345678')
  const dstLang = ref<string | null>(null)
  const result = ref<PlaygroundResult | null>(null)
  const loading = ref<boolean>(false)
  const error = ref<string | null>(null)

  async function runPipeline(): Promise<void> {
    if (!inputText.value.trim()) return
    loading.value = true
    error.value = null
    try {
      const dst = dstLang.value && dstLang.value !== 'auto' ? dstLang.value : undefined
      const res = await api.testPlayground(inputText.value.trim(), dst)
      result.value = res.data
    } catch (err: any) {
      error.value = err.response?.data?.detail || err.message || 'Pipeline execution failed.'
    } finally {
      loading.value = false
    }
  }

  function reset(): void {
    result.value = null
    error.value = null
  }

  return {
    inputText,
    dstLang,
    result,
    loading,
    error,
    runPipeline,
    reset,
  }
})
