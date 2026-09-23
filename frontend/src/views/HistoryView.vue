<script setup lang="ts">
import { ref, onMounted, computed, h } from 'vue'
import { useRouter } from 'vue-router'
import { useHistoryStore } from '../stores/history'
import { usePlaygroundStore } from '../stores/playground'
import { useUsersStore } from '../stores/users'
import { useProvidersStore } from '../stores/providers'
import { useMobile } from '../composables/useMobile'
import {
  NCard,
  NButton,
  NInput,
  NSelect,
  NTag,
  NDatePicker,
  NDrawer,
  NDrawerContent,
  NModal,
  NPagination,
  NSpin,
  NEmpty,
  NTooltip,
  NAvatar,
  NDataTable,
  useMessage,
} from 'naive-ui'
import {
  SearchOutline,
  RefreshOutline,
  DownloadOutline,
  TrashOutline,
  TimeOutline,
  PersonOutline,
  AlertCircleOutline,
  CopyOutline,
  CheckmarkOutline,
  FlaskOutline,
  FunnelOutline,
  CloseCircleOutline,
  PulseOutline,
  AppsOutline,
  ListOutline,
} from '@vicons/ionicons5'
import type { TranslationHistoryItem } from '../types'

const router = useRouter()
const historyStore = useHistoryStore()
const playgroundStore = usePlaygroundStore()
const usersStore = useUsersStore()
const providersStore = useProvidersStore()
const { isMobile } = useMobile()
const message = useMessage()

// View Mode: 'cards' or 'table'
const viewMode = ref<'cards' | 'table'>('cards')

// Prune Dialog State
const showPruneModal = ref(false)
const pruneDays = ref(30)
const pruning = ref(false)

// Copy indicator state
const copiedField = ref<string | null>(null)

// Date Range Shortcuts
const dateShortcuts = {
  Today: () => {
    const now = new Date()
    const start = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 0, 0, 0, 0)
    const end = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 23, 59, 59, 999)
    return [start.getTime(), end.getTime()] as [number, number]
  },
  Yesterday: () => {
    const now = new Date()
    const start = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1, 0, 0, 0, 0)
    const end = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1, 23, 59, 59, 999)
    return [start.getTime(), end.getTime()] as [number, number]
  },
  'Last 24 Hours': () => {
    const now = Date.now()
    return [now - 24 * 60 * 60 * 1000, now] as [number, number]
  },
  'Last 7 Days': () => {
    const now = Date.now()
    return [now - 7 * 24 * 60 * 60 * 1000, now] as [number, number]
  },
  'This Month': () => {
    const now = new Date()
    const start = new Date(now.getFullYear(), now.getMonth(), 1, 0, 0, 0, 0)
    return [start.getTime(), now.getTime()] as [number, number]
  },
}

onMounted(async () => {
  await Promise.all([
    historyStore.fetchHistory(),
    usersStore.fetchUsers(true),
    providersStore.fetchProviders(true),
  ])
})

// Search with debounce
let searchDebounceTimer: any = null
function handleSearchInput(val: string) {
  historyStore.search = val
  if (searchDebounceTimer) clearTimeout(searchDebounceTimer)
  searchDebounceTimer = setTimeout(() => {
    historyStore.page = 1
    historyStore.fetchHistory()
  }, 350)
}

// Staff user options
const staffOptions = computed(() => {
  const list = usersStore.users.map((u) => ({
    label: `${u.display_name || 'User'} (${u.username ? '@' + u.username.replace(/^@/, '') : '#' + u.user_id})`,
    value: u.user_id,
  }))
  return [{ label: 'All Staff Members', value: 0 }, ...list]
})

// Direction options
const directionOptions = [
  { label: 'All Directions', value: 'all' },
  { label: '🇲🇲 Myanmar ➔ 🇬🇧 English', value: 'my->en' },
  { label: '🇬🇧 English ➔ 🇲🇲 Myanmar', value: 'en->my' },
]

// Provider options - dynamically populated only from actually configured or observed providers
const providerOptions = computed(() => {
  const set = new Set<string>()
  // 1. Providers configured in database
  providersStore.providers.forEach((p) => {
    if (p.name) set.add(p.name)
  })
  // 2. Providers observed in history items (e.g. vsllm, cache, etc.)
  historyStore.items.forEach((it) => {
    if (it.provider) set.add(it.provider)
  })
  const sorted = Array.from(set).sort()
  const opts = sorted.map((p) => ({
    label: p,
    value: p,
  }))
  return [{ label: 'All Providers', value: 'all' }, ...opts]
})

// Status options
const statusOptions = [
  { label: 'All Statuses', value: 'all' },
  { label: '200 OK', value: '200 OK' },
  { label: 'Failed / Error', value: '500' },
]

// Prune options
const pruneOptions = [
  { label: 'Older than 14 days', value: 14 },
  { label: 'Older than 30 days (Recommended)', value: 30 },
  { label: 'Older than 60 days', value: 60 },
  { label: 'Older than 90 days', value: 90 },
]

const hasActiveFilters = computed(() => {
  return Boolean(
    historyStore.search.trim() ||
      (historyStore.selectedUser && historyStore.selectedUser !== 0) ||
      (historyStore.selectedProvider && historyStore.selectedProvider !== 'all') ||
      (historyStore.selectedDirection && historyStore.selectedDirection !== 'all') ||
      (historyStore.selectedStatus && historyStore.selectedStatus !== 'all') ||
      historyStore.dateRange
  )
})

function handleFilterChange() {
  historyStore.page = 1
  historyStore.fetchHistory()
}

function handleDateRangeChange(val: [number, number] | null) {
  historyStore.dateRange = val
  historyStore.page = 1
  historyStore.fetchHistory()
}

// Summary Metrics calculated from current page items
const metrics = computed(() => {
  const items = historyStore.items
  if (!items.length) {
    return { avgLatency: 0, policyHitRate: 0, activeStaffCount: 0 }
  }
  const totalLatency = items.reduce((acc, it) => acc + (it.latency_ms || 0), 0)
  const avgLatency = Math.round(totalLatency / items.length)

  const itemsWithHits = items.filter((it) => it.policy_hits && it.policy_hits.length > 0)
  const policyHitRate = Math.round((itemsWithHits.length / items.length) * 100)

  const uniqueUsers = new Set(items.map((it) => it.user_id))
  return {
    avgLatency,
    policyHitRate,
    activeStaffCount: uniqueUsers.size,
  }
})

// Copy text helper
async function copyToClipboard(text: string, fieldId: string) {
  try {
    await navigator.clipboard.writeText(text)
    copiedField.value = fieldId
    message.success('Copied to clipboard')
    setTimeout(() => {
      if (copiedField.value === fieldId) {
        copiedField.value = null
      }
    }, 2000)
  } catch {
    message.error('Failed to copy')
  }
}

// Export CSV
function exportToCsv() {
  if (!historyStore.items.length) {
    message.warning('No items to export')
    return
  }
  const headers = [
    'ID',
    'Timestamp',
    'User ID',
    'Staff Name',
    'Username',
    'Direction',
    'Input Text',
    'Masked Text',
    'Output Text',
    'Provider',
    'Latency (ms)',
    'Char Length',
    'Policy Hits',
    'Status',
  ]
  const rows = historyStore.items.map((item) => [
    item.id,
    `"${item.created_at || ''}"`,
    item.user_id,
    `"${(item.display_name || '').replace(/"/g, '""')}"`,
    `"${(item.username || '').replace(/"/g, '""')}"`,
    `"${item.src_lang} -> ${item.dst_lang}"`,
    `"${(item.input_text || '').replace(/"/g, '""').replace(/\n/g, ' ')}"`,
    `"${(item.masked_text || '').replace(/"/g, '""').replace(/\n/g, ' ')}"`,
    `"${(item.output_text || '').replace(/"/g, '""').replace(/\n/g, ' ')}"`,
    `"${item.provider || ''}"`,
    item.latency_ms ?? '',
    item.char_len ?? '',
    `"${(item.policy_hits || []).join('; ')}"`,
    `"${item.status || ''}"`,
  ])

  const csvContent = 'data:text/csv;charset=utf-8,\uFEFF' + [headers.join(','), ...rows.map((r) => r.join(','))].join('\n')
  const encodedUri = encodeURI(csvContent)
  const link = document.createElement('a')
  link.setAttribute('href', encodedUri)
  link.setAttribute('download', `translation_history_${new Date().toISOString().slice(0, 10)}.csv`)
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
}

// Prune Execution
async function confirmPrune() {
  pruning.value = true
  try {
    const deleted = await historyStore.prune(pruneDays.value)
    message.success(`Successfully pruned ${deleted} records older than ${pruneDays.value} days`)
    showPruneModal.value = false
  } catch (err: any) {
    message.error(`Prune failed: ${err.message || 'Unknown error'}`)
  } finally {
    pruning.value = false
  }
}

// Forward to Playground
function testInPlayground(text: string) {
  playgroundStore.inputText = text
  historyStore.closeDetail()
  router.push({ name: 'playground' })
}

// Table Columns definition for Naive UI DataTable
const tableColumns = [
  {
    title: 'ID / Time',
    key: 'id',
    width: 140,
    render(row: TranslationHistoryItem) {
      return h('div', { class: 'space-y-0.5' }, [
        h('div', { class: 'font-mono text-xs text-gray-200 font-semibold' }, `#${row.id}`),
        h('div', { class: 'text-[11px] text-gray-400 font-mono' }, row.created_at || '—'),
      ])
    },
  },
  {
    title: 'Staff Member',
    key: 'user_id',
    width: 180,
    render(row: TranslationHistoryItem) {
      return h('div', { class: 'flex items-center space-x-2' }, [
        h(
          NAvatar,
          {
            size: 'small',
            round: true,
            class: 'bg-gradient-to-tr from-cyan-600 to-indigo-600 text-white font-bold text-xs flex-shrink-0',
          },
          { default: () => (row.display_name ? row.display_name.charAt(0).toUpperCase() : 'U') }
        ),
        h('div', { class: 'min-w-0' }, [
          h('div', { class: 'text-xs font-semibold text-gray-200 truncate' }, row.display_name || `ID: ${row.user_id}`),
          row.username
            ? h(
                'a',
                {
                  href: `https://t.me/${row.username.replace(/^@/, '')}`,
                  target: '_blank',
                  rel: 'noopener noreferrer',
                  class: 'text-[11px] text-cyan-400 hover:underline font-mono truncate block',
                },
                `@${row.username.replace(/^@/, '')}`
              )
            : h('span', { class: 'text-[10px] text-gray-500 font-mono' }, `UID: ${row.user_id}`),
        ]),
      ])
    },
  },
  {
    title: 'Direction',
    key: 'direction',
    width: 120,
    render(row: TranslationHistoryItem) {
      const isMyToEn = row.src_lang === 'my' && row.dst_lang === 'en'
      return h(
        NTag,
        {
          size: 'small',
          type: isMyToEn ? 'info' : 'primary',
          class: 'font-mono text-[11px] font-semibold tracking-tight',
        },
        { default: () => `${row.src_lang.toUpperCase()} ➔ ${row.dst_lang.toUpperCase()}` }
      )
    },
  },
  {
    title: 'Input Message Preview',
    key: 'input_text',
    render(row: TranslationHistoryItem) {
      return h('div', { class: 'text-xs text-gray-300 line-clamp-2 font-sans max-w-md' }, row.input_text)
    },
  },
  {
    title: 'Translated Output',
    key: 'output_text',
    render(row: TranslationHistoryItem) {
      return h('div', { class: 'text-xs text-emerald-300/90 line-clamp-2 font-sans max-w-md' }, row.output_text)
    },
  },
  {
    title: 'Provider / Latency',
    key: 'provider',
    width: 140,
    render(row: TranslationHistoryItem) {
      const lat = row.latency_ms ?? 0
      const latColor = lat < 1200 ? 'text-emerald-400' : lat < 3000 ? 'text-amber-400' : 'text-rose-400'
      return h('div', { class: 'space-y-0.5' }, [
        h('div', { class: 'text-[11px] font-mono text-cyan-300 font-medium' }, row.provider || 'default'),
        h('div', { class: `text-[10px] font-mono ${latColor}` }, `${lat} ms (${row.char_len ?? 0} chars)`),
      ])
    },
  },
  {
    title: 'Policy Hits',
    key: 'policy_hits',
    width: 140,
    render(row: TranslationHistoryItem) {
      if (!row.policy_hits || !row.policy_hits.length) {
        return h('span', { class: 'text-[11px] text-gray-500 italic' }, 'None')
      }
      return h(
        'div',
        { class: 'flex flex-wrap gap-1' },
        row.policy_hits.map((hit) =>
          h(
            NTag,
            { size: 'tiny', type: 'warning', class: 'font-mono text-[10px]' },
            { default: () => `⟦${hit}⟧` }
          )
        )
      )
    },
  },
  {
    title: 'Action',
    key: 'actions',
    width: 80,
    render(row: TranslationHistoryItem) {
      return h(
        NButton,
        {
          size: 'tiny',
          type: 'primary',
          secondary: true,
          onClick: () => historyStore.openDetail(row),
        },
        { default: () => 'Inspect' }
      )
    },
  },
]
</script>

<template>
  <div class="space-y-6 max-w-7xl mx-auto">
    <!-- Top Header & Action Controls -->
    <div class="flex flex-col md:flex-row md:items-center justify-between gap-4">
      <div>
        <div class="flex items-center space-x-2.5">
          <h1 class="text-2xl font-bold text-gray-100 tracking-tight flex items-center gap-2">
            <span>Translation History & Staff Audits</span>
          </h1>
          <span
            v-if="historyStore.liveStreaming"
            class="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
            title="Real-time SSE Live Stream connected"
          >
            <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
            Live Stream
          </span>
          <span
            v-else
            class="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-medium bg-gray-800 text-gray-400 border border-gray-700"
          >
            Stream Paused
          </span>
        </div>
        <p class="text-xs text-gray-400 mt-1">
          Full message text visibility for staff operational audit, quality inspection, and term-masking verification.
        </p>
      </div>

      <!-- Action Buttons -->
      <div class="flex flex-wrap items-center gap-2">
        <!-- Live Stream Toggle -->
        <NTooltip trigger="hover">
          <template #trigger>
            <NButton
              size="small"
              :secondary="!historyStore.liveStreaming"
              :type="historyStore.liveStreaming ? 'success' : 'default'"
              @click="historyStore.liveStreaming = !historyStore.liveStreaming"
            >
              <template #icon>
                <PulseOutline />
              </template>
              {{ historyStore.liveStreaming ? 'Live Active' : 'Resume Live' }}
            </NButton>
          </template>
          Toggle real-time streaming updates
        </NTooltip>

        <!-- View Mode Switch -->
        <div class="flex items-center rounded-lg bg-gray-900 border border-gray-800 p-0.5">
          <button
            type="button"
            class="px-2.5 py-1 text-xs rounded-md transition-colors flex items-center gap-1"
            :class="viewMode === 'cards' ? 'bg-cyan-500/20 text-cyan-300 font-semibold' : 'text-gray-400 hover:text-gray-200'"
            @click="viewMode = 'cards'"
            title="Card Feed View"
          >
            <AppsOutline class="w-3.5 h-3.5" />
            <span class="hidden sm:inline">Cards</span>
          </button>
          <button
            type="button"
            class="px-2.5 py-1 text-xs rounded-md transition-colors flex items-center gap-1"
            :class="viewMode === 'table' ? 'bg-cyan-500/20 text-cyan-300 font-semibold' : 'text-gray-400 hover:text-gray-200'"
            @click="viewMode = 'table'"
            title="Dense Table View"
          >
            <ListOutline class="w-3.5 h-3.5" />
            <span class="hidden sm:inline">Table</span>
          </button>
        </div>

        <!-- Export CSV -->
        <NButton secondary size="small" @click="exportToCsv" title="Export currently loaded translations to CSV">
          <template #icon>
            <DownloadOutline />
          </template>
          Export CSV
        </NButton>

        <!-- Prune Button -->
        <NButton secondary size="small" type="warning" @click="showPruneModal = true" title="Clean older records to save database storage">
          <template #icon>
            <TrashOutline />
          </template>
          Prune Retention
        </NButton>

        <!-- Refresh Button -->
        <NButton secondary size="small" @click="() => historyStore.fetchHistory()" :loading="historyStore.loading">
          <template #icon>
            <RefreshOutline />
          </template>
          Refresh
        </NButton>
      </div>
    </div>

    <!-- Quick Telemetry & Audit Metrics Cards -->
    <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
      <!-- Metric 1: Total Translations in Database -->
      <div class="p-3.5 rounded-xl bg-gray-900/80 border border-gray-800/80 backdrop-blur-sm space-y-1">
        <div class="text-[11px] text-gray-400 font-medium flex items-center justify-between">
          <span>Total Audited Records</span>
          <TimeOutline class="w-3.5 h-3.5 text-cyan-400" />
        </div>
        <div class="text-xl font-bold font-mono text-cyan-400">
          {{ historyStore.total.toLocaleString() }}
        </div>
        <div class="text-[10px] text-gray-500">
          Page {{ historyStore.page }} of {{ historyStore.totalPages || 1 }}
        </div>
      </div>

      <!-- Metric 2: Active Staff Contributing -->
      <div class="p-3.5 rounded-xl bg-gray-900/80 border border-gray-800/80 backdrop-blur-sm space-y-1">
        <div class="text-[11px] text-gray-400 font-medium flex items-center justify-between">
          <span>Staff in Batch</span>
          <PersonOutline class="w-3.5 h-3.5 text-indigo-400" />
        </div>
        <div class="text-xl font-bold font-mono text-indigo-400">
          {{ metrics.activeStaffCount }}
        </div>
        <div class="text-[10px] text-gray-500">
          Unique operators audited
        </div>
      </div>

      <!-- Metric 3: Average Latency -->
      <div class="p-3.5 rounded-xl bg-gray-900/80 border border-gray-800/80 backdrop-blur-sm space-y-1">
        <div class="text-[11px] text-gray-400 font-medium flex items-center justify-between">
          <span>Batch Avg Latency</span>
          <PulseOutline class="w-3.5 h-3.5 text-emerald-400" />
        </div>
        <div
          class="text-xl font-bold font-mono"
          :class="metrics.avgLatency < 1200 ? 'text-emerald-400' : 'text-amber-400'"
        >
          {{ metrics.avgLatency }} ms
        </div>
        <div class="text-[10px] text-gray-500">
          End-to-end pipeline speed
        </div>
      </div>

      <!-- Metric 4: Policy Filter Interception Rate -->
      <div class="p-3.5 rounded-xl bg-gray-900/80 border border-gray-800/80 backdrop-blur-sm space-y-1">
        <div class="text-[11px] text-gray-400 font-medium flex items-center justify-between">
          <span>Policy Interception</span>
          <AlertCircleOutline class="w-3.5 h-3.5 text-amber-400" />
        </div>
        <div class="text-xl font-bold font-mono text-amber-400">
          {{ metrics.policyHitRate }}%
        </div>
        <div class="text-[10px] text-gray-500">
          Protected sensitive concepts
        </div>
      </div>
    </div>

    <!-- Advanced Filter & Search Bar -->
    <NCard class="glass-panel border-gray-800 rounded-xl" :bordered="false">
      <div class="space-y-3">
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-12 gap-3">
          <!-- Text Search (Input / Output / Username) -->
          <div class="lg:col-span-4">
            <NInput
              :value="historyStore.search"
              placeholder="Search Burmese / English text or @username..."
              size="small"
              clearable
              @update:value="handleSearchInput"
              @clear="() => { historyStore.search = ''; handleFilterChange() }"
            >
              <template #prefix>
                <SearchOutline class="w-4 h-4 text-gray-500 mr-1" />
              </template>
            </NInput>
          </div>

          <!-- Staff Selector -->
          <div class="lg:col-span-3">
            <NSelect
              v-model:value="historyStore.selectedUser"
              :options="staffOptions"
              size="small"
              placeholder="Filter by Staff Member"
              @update:value="handleFilterChange"
            />
          </div>

          <!-- Language Direction -->
          <div class="lg:col-span-2">
            <NSelect
              v-model:value="historyStore.selectedDirection"
              :options="directionOptions"
              size="small"
              placeholder="Direction"
              @update:value="handleFilterChange"
            />
          </div>

          <!-- Provider Select -->
          <div class="lg:col-span-3">
            <NSelect
              v-model:value="historyStore.selectedProvider"
              :options="providerOptions"
              size="small"
              placeholder="Provider"
              @update:value="handleFilterChange"
            />
          </div>
        </div>

        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-12 gap-3 items-center">
          <!-- Date Time Range Picker -->
          <div class="lg:col-span-6">
            <NDatePicker
              :value="historyStore.dateRange"
              type="datetimerange"
              clearable
              size="small"
              :shortcuts="dateShortcuts"
              start-placeholder="Start Date & Time"
              end-placeholder="End Date & Time"
              @update:value="handleDateRangeChange"
            />
          </div>

          <!-- Status Filter -->
          <div class="lg:col-span-3">
            <NSelect
              v-model:value="historyStore.selectedStatus"
              :options="statusOptions"
              size="small"
              placeholder="Status"
              @update:value="handleFilterChange"
            />
          </div>

          <!-- Reset Filter Action -->
          <div class="lg:col-span-3 flex justify-end">
            <NButton
              v-if="hasActiveFilters"
              quaternary
              size="small"
              type="warning"
              @click="historyStore.resetFilters()"
            >
              <template #icon>
                <CloseCircleOutline />
              </template>
              Reset All Filters
            </NButton>
          </div>
        </div>

        <!-- Filter Tags Bar -->
        <div
          v-if="hasActiveFilters"
          class="pt-2 border-t border-gray-800/80 flex flex-wrap items-center gap-1.5 text-xs"
        >
          <span class="text-gray-500 font-medium flex items-center gap-1">
            <FunnelOutline class="w-3.5 h-3.5 text-cyan-400" />
            Active Filters:
          </span>

          <NTag
            v-if="historyStore.search.trim()"
            size="small"
            type="info"
            closable
            @close="() => { historyStore.search = ''; handleFilterChange() }"
            class="text-[11px]"
          >
            Keyword: "{{ historyStore.search }}"
          </NTag>

          <NTag
            v-if="historyStore.selectedUser && historyStore.selectedUser !== 0"
            size="small"
            type="info"
            closable
            @close="() => { historyStore.selectedUser = null; handleFilterChange() }"
            class="text-[11px]"
          >
            Staff User: {{ historyStore.selectedUser }}
          </NTag>

          <NTag
            v-if="historyStore.selectedDirection && historyStore.selectedDirection !== 'all'"
            size="small"
            type="info"
            closable
            @close="() => { historyStore.selectedDirection = null; handleFilterChange() }"
            class="text-[11px] font-mono"
          >
            Direction: {{ historyStore.selectedDirection }}
          </NTag>

          <NTag
            v-if="historyStore.selectedProvider && historyStore.selectedProvider !== 'all'"
            size="small"
            type="info"
            closable
            @close="() => { historyStore.selectedProvider = null; handleFilterChange() }"
            class="text-[11px] font-mono"
          >
            Provider: {{ historyStore.selectedProvider }}
          </NTag>

          <NTag
            v-if="historyStore.dateRange"
            size="small"
            type="info"
            closable
            @close="() => { historyStore.dateRange = null; handleFilterChange() }"
            class="text-[11px] font-mono"
          >
            Date Filtered
          </NTag>
        </div>
      </div>
    </NCard>

    <!-- Loading State -->
    <div v-if="historyStore.loading" class="py-16 text-center">
      <NSpin size="large" />
      <div class="mt-3 text-xs text-gray-400">Loading translation audit records...</div>
    </div>

    <!-- Empty State -->
    <div
      v-else-if="!historyStore.items.length"
      class="py-16 text-center bg-gray-900/40 rounded-xl border border-gray-800"
    >
      <NEmpty description="No translation history found matching your filters.">
        <template #extra>
          <NButton
            v-if="hasActiveFilters"
            secondary
            size="small"
            type="primary"
            @click="historyStore.resetFilters()"
          >
            Clear Filters
          </NButton>
        </template>
      </NEmpty>
    </div>

    <!-- Card Feed View Mode -->
    <div v-else-if="viewMode === 'cards'" class="space-y-3.5">
      <div
        v-for="item in historyStore.items"
        :key="item.id"
        class="group p-4 rounded-xl bg-gray-900/70 hover:bg-gray-900 border border-gray-800 hover:border-gray-700/80 transition-all shadow-sm hover:shadow-md"
      >
        <!-- Card Top Bar: Staff Identity, Direction & Timestamp -->
        <div class="flex flex-wrap items-center justify-between gap-2 pb-2.5 border-b border-gray-800/70">
          <div class="flex items-center space-x-2.5 min-w-0">
            <NAvatar
              round
              size="small"
              class="bg-gradient-to-tr from-cyan-600 to-indigo-600 text-white font-bold text-xs flex-shrink-0"
            >
              {{ item.display_name ? item.display_name.charAt(0).toUpperCase() : 'U' }}
            </NAvatar>
            <div class="min-w-0">
              <div class="flex items-center space-x-2">
                <span class="text-xs font-semibold text-gray-100 truncate">
                  {{ item.display_name || 'Staff User' }}
                </span>
                <a
                  v-if="item.username"
                  :href="`https://t.me/${item.username.replace(/^@/, '')}`"
                  target="_blank"
                  rel="noopener noreferrer"
                  class="text-[11px] text-cyan-400 hover:underline font-mono truncate"
                >
                  @{{ item.username.replace(/^@/, '') }}
                </a>
              </div>
              <div class="text-[10px] text-gray-500 font-mono">
                UID: {{ item.user_id }}
              </div>
            </div>
          </div>

          <div class="flex items-center space-x-2">
            <!-- Language Direction Pill -->
            <NTag
              size="small"
              :type="item.src_lang === 'my' ? 'info' : 'primary'"
              class="font-mono text-[11px] font-semibold"
            >
              {{ item.src_lang.toUpperCase() }} ➔ {{ item.dst_lang.toUpperCase() }}
            </NTag>

            <!-- Timestamp Tag -->
            <span class="text-[11px] text-gray-400 font-mono flex items-center gap-1">
              <TimeOutline class="w-3.5 h-3.5 text-gray-500" />
              {{ item.created_at || '—' }}
            </span>
          </div>
        </div>

        <!-- Card Body: Side-by-side or Stacked Message Previews -->
        <div class="grid grid-cols-1 md:grid-cols-2 gap-3 py-3 text-xs">
          <!-- Input Message Snippet -->
          <div class="p-3 rounded-lg bg-gray-950/60 border border-gray-800/60 space-y-1">
            <div class="text-[10px] uppercase tracking-wider font-semibold text-gray-400 flex items-center justify-between">
              <span>Staff Input ({{ item.src_lang.toUpperCase() }})</span>
              <button
                type="button"
                class="text-gray-500 hover:text-cyan-400 transition-colors"
                title="Copy input text"
                @click="copyToClipboard(item.input_text, `in_${item.id}`)"
              >
                <CopyOutline class="w-3.5 h-3.5" />
              </button>
            </div>
            <div class="text-gray-200 line-clamp-3 leading-relaxed whitespace-pre-wrap font-sans">
              {{ item.input_text }}
            </div>
          </div>

          <!-- Translated Output Snippet -->
          <div class="p-3 rounded-lg bg-emerald-950/20 border border-emerald-900/30 space-y-1">
            <div class="text-[10px] uppercase tracking-wider font-semibold text-emerald-400 flex items-center justify-between">
              <span>Delivered Output ({{ item.dst_lang.toUpperCase() }})</span>
              <button
                type="button"
                class="text-emerald-500 hover:text-emerald-300 transition-colors"
                title="Copy translated text"
                @click="copyToClipboard(item.output_text, `out_${item.id}`)"
              >
                <CopyOutline class="w-3.5 h-3.5" />
              </button>
            </div>
            <div class="text-emerald-200/90 line-clamp-3 leading-relaxed whitespace-pre-wrap font-sans">
              {{ item.output_text }}
            </div>
          </div>
        </div>

        <!-- Card Footer: Telemetry Tags & Quick Inspect Button -->
        <div class="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-gray-800/60 text-xs">
          <div class="flex flex-wrap items-center gap-1.5">
            <!-- Provider Pill -->
            <span class="px-2 py-0.5 rounded font-mono text-[10px] bg-cyan-950/60 text-cyan-300 border border-cyan-800/40">
              {{ item.provider || 'default' }}
            </span>

            <!-- Latency Pill -->
            <span
              class="px-2 py-0.5 rounded font-mono text-[10px] border"
              :class="
                (item.latency_ms ?? 0) < 1200
                  ? 'bg-emerald-950/50 text-emerald-400 border-emerald-800/40'
                  : (item.latency_ms ?? 0) < 3000
                  ? 'bg-amber-950/50 text-amber-400 border-amber-800/40'
                  : 'bg-rose-950/50 text-rose-400 border-rose-800/40'
              "
            >
              {{ item.latency_ms ?? 0 }} ms
            </span>

            <!-- Character Length -->
            <span class="px-2 py-0.5 rounded font-mono text-[10px] bg-gray-800 text-gray-400">
              {{ item.char_len ?? item.input_text.length }} chars
            </span>

            <!-- Policy Hits Pills -->
            <template v-if="item.policy_hits && item.policy_hits.length">
              <span
                v-for="hName in item.policy_hits"
                :key="hName"
                class="px-1.5 py-0.5 rounded font-mono text-[10px] bg-amber-500/10 text-amber-300 border border-amber-500/20"
              >
                ⟦{{ hName }}⟧
              </span>
            </template>
          </div>

          <!-- Inspect Action -->
          <NButton
            size="tiny"
            type="primary"
            secondary
            @click="historyStore.openDetail(item)"
          >
            Inspect 3-Stage Pipeline
          </NButton>
        </div>
      </div>
    </div>

    <!-- Table View Mode -->
    <NCard v-else class="glass-panel border-gray-800 rounded-xl" :bordered="false">
      <NDataTable
        :columns="tableColumns"
        :data="historyStore.items"
        :loading="historyStore.loading"
        :row-key="(row) => row.id"
        :scroll-x="960"
      />
    </NCard>

    <!-- Pagination Controls -->
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pt-2">
      <div class="text-xs text-gray-400 font-mono">
        Showing {{ historyStore.items.length }} of {{ historyStore.total }} records
      </div>
      <NPagination
        :page="historyStore.page"
        :page-size="historyStore.pageSize"
        :page-count="historyStore.totalPages"
        :page-sizes="[10, 20, 50, 100]"
        show-size-picker
        @update:page="historyStore.setPage"
        @update:page-size="historyStore.setPageSize"
      />
    </div>

    <!-- 3-STAGE VISUAL PIPELINE INSPECTOR DRAWER -->
    <NDrawer
      v-model:show="historyStore.showDetailModal"
      :width="isMobile ? '100%' : 540"
      placement="right"
    >
      <NDrawerContent title="Translation Audit & Policy Inspector" closable>
        <div v-if="historyStore.selectedItem" class="space-y-6 text-xs pb-6">
          <!-- Header Meta Card -->
          <div class="p-4 rounded-xl bg-gray-900 border border-gray-800 space-y-2.5">
            <div class="flex items-center justify-between">
              <span class="text-gray-400 font-medium">Record ID</span>
              <span class="font-mono text-cyan-300 font-bold text-sm">#{{ historyStore.selectedItem.id }}</span>
            </div>
            <div class="flex items-center justify-between">
              <span class="text-gray-400 font-medium">Timestamp</span>
              <span class="font-mono text-gray-200">{{ historyStore.selectedItem.created_at }}</span>
            </div>
            <div class="flex items-center justify-between">
              <span class="text-gray-400 font-medium">Staff Member</span>
              <span class="font-semibold text-gray-100">
                {{ historyStore.selectedItem.display_name || 'Staff User' }}
              </span>
            </div>
            <div v-if="historyStore.selectedItem.username" class="flex items-center justify-between">
              <span class="text-gray-400 font-medium">Telegram Handle</span>
              <a
                :href="`https://t.me/${historyStore.selectedItem.username.replace(/^@/, '')}`"
                target="_blank"
                rel="noopener noreferrer"
                class="font-mono text-cyan-400 hover:underline"
              >
                @{{ historyStore.selectedItem.username.replace(/^@/, '') }}
              </a>
            </div>
            <div class="flex items-center justify-between">
              <span class="text-gray-400 font-medium">Telegram User ID</span>
              <span class="font-mono text-emerald-400">{{ historyStore.selectedItem.user_id }}</span>
            </div>
            <div class="flex items-center justify-between">
              <span class="text-gray-400 font-medium">Translation Route</span>
              <NTag size="small" type="primary" class="font-mono font-semibold">
                {{ historyStore.selectedItem.src_lang.toUpperCase() }} ➔ {{ historyStore.selectedItem.dst_lang.toUpperCase() }}
              </NTag>
            </div>
          </div>

          <!-- STAGE 1: RAW INPUT -->
          <div class="space-y-1.5">
            <div class="flex items-center justify-between">
              <div class="flex items-center space-x-2">
                <span class="w-5 h-5 rounded-full bg-cyan-500/20 text-cyan-400 font-mono font-bold flex items-center justify-center text-[10px]">
                  1
                </span>
                <span class="font-semibold text-gray-200">Stage 1: Original Staff Input</span>
              </div>
              <NButton
                size="tiny"
                secondary
                @click="copyToClipboard(historyStore.selectedItem.input_text, 'stage1')"
              >
                <template #icon>
                  <CheckmarkOutline v-if="copiedField === 'stage1'" class="text-emerald-400" />
                  <CopyOutline v-else />
                </template>
                {{ copiedField === 'stage1' ? 'Copied' : 'Copy' }}
              </NButton>
            </div>
            <div class="p-3.5 rounded-xl bg-gray-950 border border-gray-800 text-gray-200 font-sans leading-relaxed whitespace-pre-wrap select-text">
              {{ historyStore.selectedItem.input_text }}
            </div>
          </div>

          <!-- STAGE 2: POLICY MASKING INTERMEDIATE -->
          <div class="space-y-1.5">
            <div class="flex items-center justify-between">
              <div class="flex items-center space-x-2">
                <span class="w-5 h-5 rounded-full bg-amber-500/20 text-amber-400 font-mono font-bold flex items-center justify-center text-[10px]">
                  2
                </span>
                <span class="font-semibold text-gray-200">Stage 2: Policy Masking Interception</span>
              </div>
              <NButton
                v-if="historyStore.selectedItem.masked_text"
                size="tiny"
                secondary
                @click="copyToClipboard(historyStore.selectedItem.masked_text, 'stage2')"
              >
                <template #icon>
                  <CheckmarkOutline v-if="copiedField === 'stage2'" class="text-emerald-400" />
                  <CopyOutline v-else />
                </template>
                {{ copiedField === 'stage2' ? 'Copied' : 'Copy' }}
              </NButton>
            </div>

            <!-- Intercepted Text Container -->
            <div class="p-3.5 rounded-xl bg-gray-950 border border-amber-900/30 text-amber-200/90 font-sans leading-relaxed whitespace-pre-wrap select-text">
              <div v-if="historyStore.selectedItem.masked_text">
                {{ historyStore.selectedItem.masked_text }}
              </div>
              <div v-else class="text-gray-500 italic">
                Direct passthrough (No policy mask applied or relaxed destination route).
              </div>
            </div>

            <!-- Detected Concepts Highlight Pills -->
            <div v-if="historyStore.selectedItem.policy_hits && historyStore.selectedItem.policy_hits.length" class="space-y-1 pt-1">
              <div class="text-[11px] text-gray-400 font-medium">Sensitive Concepts Intercepted:</div>
              <div class="flex flex-wrap gap-1.5">
                <span
                  v-for="c in historyStore.selectedItem.policy_hits"
                  :key="c"
                  class="px-2 py-0.5 rounded font-mono text-[11px] bg-amber-500/10 text-amber-300 border border-amber-500/30 font-semibold"
                >
                  ⟦{{ c }}⟧
                </span>
              </div>
            </div>
          </div>

          <!-- STAGE 3: FINAL DELIVERED TRANSLATION -->
          <div class="space-y-1.5">
            <div class="flex items-center justify-between">
              <div class="flex items-center space-x-2">
                <span class="w-5 h-5 rounded-full bg-emerald-500/20 text-emerald-400 font-mono font-bold flex items-center justify-center text-[10px]">
                  3
                </span>
                <span class="font-semibold text-gray-200">Stage 3: Delivered Translation</span>
              </div>
              <NButton
                size="tiny"
                secondary
                type="success"
                @click="copyToClipboard(historyStore.selectedItem.output_text, 'stage3')"
              >
                <template #icon>
                  <CheckmarkOutline v-if="copiedField === 'stage3'" class="text-emerald-400" />
                  <CopyOutline v-else />
                </template>
                {{ copiedField === 'stage3' ? 'Copied' : 'Copy' }}
              </NButton>
            </div>
            <div class="p-3.5 rounded-xl bg-gray-950 border border-emerald-900/40 text-emerald-200 font-sans leading-relaxed whitespace-pre-wrap select-text">
              {{ historyStore.selectedItem.output_text }}
            </div>
          </div>

          <!-- TELEMETRY & ROUTING FOOTPRINT -->
          <div class="p-4 rounded-xl bg-gray-900 border border-gray-800 space-y-2">
            <div class="text-xs font-semibold text-gray-300">Technical Telemetry</div>
            <div class="grid grid-cols-2 gap-2 text-[11px]">
              <div>
                <span class="text-gray-500">Upstream Provider: </span>
                <span class="font-mono text-cyan-300 font-medium">{{ historyStore.selectedItem.provider || 'default' }}</span>
              </div>
              <div>
                <span class="text-gray-500">Total Latency: </span>
                <span class="font-mono font-bold text-emerald-400">{{ historyStore.selectedItem.latency_ms }} ms</span>
              </div>
              <div>
                <span class="text-gray-500">Input Character Count: </span>
                <span class="font-mono text-gray-300">{{ historyStore.selectedItem.char_len }}</span>
              </div>
              <div>
                <span class="text-gray-500">Status Response: </span>
                <span class="font-mono text-gray-300">{{ historyStore.selectedItem.status }}</span>
              </div>
            </div>
          </div>

          <!-- Quick Action: Test in Playground -->
          <div class="pt-2">
            <NButton
              block
              type="primary"
              secondary
              @click="testInPlayground(historyStore.selectedItem.input_text)"
            >
              <template #icon>
                <FlaskOutline />
              </template>
              Test This Message in Playground
            </NButton>
          </div>
        </div>
      </NDrawerContent>
    </NDrawer>

    <!-- PRUNE RETENTION MODAL -->
    <NModal
      v-model:show="showPruneModal"
      preset="dialog"
      title="Prune Translation History"
      positive-text="Confirm Prune"
      negative-text="Cancel"
      type="warning"
      :loading="pruning"
      @positive-click="confirmPrune"
      @negative-click="showPruneModal = false"
    >
      <div class="space-y-4 text-xs py-2">
        <p class="text-gray-300">
          To prevent exceeding Supabase free-tier database storage limits, prune older translation history records.
        </p>
        <div>
          <label class="block text-gray-400 mb-1.5 font-medium">Select Retention Period:</label>
          <NSelect v-model:value="pruneDays" :options="pruneOptions" />
        </div>
        <div class="p-3 rounded-lg bg-amber-950/30 border border-amber-800/40 text-amber-300/90 text-[11px]">
          ⚠️ Records older than {{ pruneDays }} days will be permanently removed from PostgreSQL. System telemetry logs in Audit Logs will remain unaffected.
        </div>
      </div>
    </NModal>
  </div>
</template>

<style scoped>
.glass-panel {
  background: rgba(17, 24, 39, 0.7);
  backdrop-filter: blur(12px);
}
</style>
