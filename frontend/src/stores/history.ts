import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '../api'
import type { TranslationHistoryItem } from '../types'

export const useHistoryStore = defineStore('history', () => {
  const items = ref<TranslationHistoryItem[]>([])
  const total = ref<number>(0)
  const page = ref<number>(1)
  const pageSize = ref<number>(20)
  const totalPages = ref<number>(0)
  const search = ref<string>('')
  const selectedUser = ref<number | null>(null)
  const selectedProvider = ref<string | null>(null)
  const selectedDirection = ref<string | null>(null)
  const selectedStatus = ref<string | null>(null)
  const dateRange = ref<[number, number] | null>(null)
  const loading = ref<boolean>(false)
  const liveStreaming = ref<boolean>(true)

  // Detail Modal State
  const selectedItem = ref<TranslationHistoryItem | null>(null)
  const showDetailModal = ref<boolean>(false)

  async function fetchHistory(silent = false): Promise<void> {
    if (!silent) {
      loading.value = true
    }
    try {
      const params: Record<string, any> = {
        page: page.value,
        page_size: pageSize.value,
      }
      if (search.value.trim()) {
        params.search = search.value.trim()
      }
      if (selectedUser.value && selectedUser.value !== 0) {
        params.user_id = selectedUser.value
      }
      if (selectedProvider.value && selectedProvider.value !== 'all') {
        params.provider = selectedProvider.value
      }
      if (selectedStatus.value && selectedStatus.value !== 'all') {
        params.status = selectedStatus.value
      }
      if (selectedDirection.value && selectedDirection.value !== 'all') {
        const [s, d] = selectedDirection.value.split('->')
        if (s) params.src_lang = s
        if (d) params.dst_lang = d
      }
      if (dateRange.value && dateRange.value.length === 2) {
        params.start_time = dateRange.value[0]
        params.end_time = dateRange.value[1]
      }

      const res = await api.getHistory(params)
      items.value = res.data.items || []
      total.value = res.data.total || 0
      totalPages.value = res.data.total_pages || 0
    } finally {
      if (!silent) {
        loading.value = false
      }
    }
  }

  function addLiveHistory(item: TranslationHistoryItem): void {
    if (!liveStreaming.value) return
    // Only prepend on page 1 when no active text search filter is active
    if (page.value === 1 && !search.value.trim()) {
      // Avoid duplicate by id
      const idx = items.value.findIndex((x) => x.id === item.id)
      if (idx === -1) {
        items.value.unshift(item)
        if (items.value.length > pageSize.value) {
          items.value.pop()
        }
        total.value += 1
      }
    }
  }

  function openDetail(item: TranslationHistoryItem): void {
    selectedItem.value = item
    showDetailModal.value = true
  }

  function closeDetail(): void {
    showDetailModal.value = false
    selectedItem.value = null
  }

  function setPage(newPage: number): void {
    page.value = newPage
    fetchHistory()
  }

  function setPageSize(newPageSize: number): void {
    pageSize.value = newPageSize
    page.value = 1
    fetchHistory()
  }

  function resetFilters(): void {
    search.value = ''
    selectedUser.value = null
    selectedProvider.value = null
    selectedDirection.value = null
    selectedStatus.value = null
    dateRange.value = null
    page.value = 1
    fetchHistory()
  }

  async function prune(days: number): Promise<number> {
    const res = await api.pruneHistory(days)
    await fetchHistory()
    return res.data.deleted_count
  }

  return {
    items,
    total,
    page,
    pageSize,
    totalPages,
    search,
    selectedUser,
    selectedProvider,
    selectedDirection,
    selectedStatus,
    dateRange,
    loading,
    liveStreaming,
    selectedItem,
    showDetailModal,
    fetchHistory,
    addLiveHistory,
    openDetail,
    closeDetail,
    setPage,
    setPageSize,
    resetFilters,
    prune,
  }
})
