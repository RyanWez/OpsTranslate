<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, h } from 'vue'
import { useRouter } from 'vue-router'
import { useLogsStore } from '../stores/logs'
import { usePlaygroundStore } from '../stores/playground'
import { useMobile } from '../composables/useMobile'
import {
  NCard,
  NButton,
  NDataTable,
  NTag,
  NSelect,
  NInput,
  NDrawer,
  NDrawerContent,
  NDatePicker,
} from 'naive-ui'
import {
  RefreshOutline,
  SearchOutline,
  DownloadOutline,
  FlaskOutline,
  CloseCircleOutline,
  FilterOutline,
} from '@vicons/ionicons5'
import type { UsageLogItem } from '../types'

const router = useRouter()
const logsStore = useLogsStore()
const playgroundStore = usePlaygroundStore()
const { isMobile } = useMobile()

onMounted(() => {
  logsStore.startLiveSync(3000)
})

onUnmounted(() => {
  logsStore.stopLiveSync()
})

const searchQuery = ref('')
const selectedProvider = ref<string | null>(null)
const selectedLog = ref<UsageLogItem | null>(null)
const showDetailDrawer = ref(false)

const limitOptions = [
  { label: 'Latest 50 logs', value: 50 },
  { label: 'Latest 100 logs', value: 100 },
  { label: 'Latest 200 logs', value: 200 },
  { label: 'Latest 500 logs', value: 500 },
]

// Professional Date Shortcuts for quick 1-click filtering
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

function handleLimitChange(val: number) {
  logsStore.limit = val
  logsStore.fetchLogs()
}

function handleDateRangeChange(val: [number, number] | null) {
  logsStore.dateRange = val
  logsStore.fetchLogs()
}

const providerOptions = computed(() => {
  const set = new Set<string>()
  logsStore.logs.forEach((l) => {
    if (l.provider) set.add(l.provider)
  })
  const opts = Array.from(set).map((p) => ({ label: p, value: p }))
  return [{ label: 'All Providers', value: 'all' }, ...opts]
})

function handleProviderSelect(val: string) {
  selectedProvider.value = val === 'all' ? null : val
  logsStore.selectedProvider = selectedProvider.value
  logsStore.fetchLogs()
}

const hasActiveFilters = computed(() => {
  return Boolean(
    searchQuery.value.trim() ||
      (selectedProvider.value && selectedProvider.value !== 'all') ||
      (logsStore.dateRange && logsStore.dateRange.length === 2)
  )
})

function clearAllFilters() {
  searchQuery.value = ''
  selectedProvider.value = null
  logsStore.selectedProvider = null
  logsStore.dateRange = null
  logsStore.fetchLogs()
}

function formatTimestamp(ts: number): string {
  const d = new Date(ts)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

const filteredLogs = computed(() => {
  let list: UsageLogItem[] = logsStore.logs

  if (selectedProvider.value && selectedProvider.value !== 'all') {
    const pTarget = selectedProvider.value.toLowerCase()
    list = list.filter((l: UsageLogItem) => (l.provider || '').toLowerCase() === pTarget)
  }

  if (logsStore.dateRange && logsStore.dateRange.length === 2) {
    const [startMs, endMs] = logsStore.dateRange
    list = list.filter((l: UsageLogItem) => {
      if (!l.created_at && !l.timestamp) return false
      let timeMs: number
      if (l.timestamp) {
        timeMs = l.timestamp > 1e11 ? l.timestamp : l.timestamp * 1000
      } else {
        timeMs = new Date(l.created_at!.replace(' ', 'T')).getTime()
      }
      if (isNaN(timeMs)) return false
      return timeMs >= startMs && timeMs <= endMs
    })
  }

  if (searchQuery.value.trim()) {
    const q = searchQuery.value.trim().toLowerCase()
    list = list.filter(
      (l: UsageLogItem) =>
        String(l.user_id).includes(q) ||
        (l.provider || '').toLowerCase().includes(q) ||
        (l.policy_hits || []).some((p: string) => p.toLowerCase().includes(q))
    )
  }
  return list
})

function openDetail(row: UsageLogItem) {
  selectedLog.value = row
  showDetailDrawer.value = true
}

function sendToPlayground(conceptHit?: string) {
  if (conceptHit) {
    playgroundStore.inputText = `Testing concept: ${conceptHit}`
  }
  showDetailDrawer.value = false
  router.push({ name: 'playground' })
}

function exportToCsv() {
  if (!filteredLogs.value.length) return
  const headers = ['ID', 'Timestamp', 'UserID', 'Provider', 'CharLen', 'LatencyMs', 'StatusCode', 'PolicyHits']
  const rows = filteredLogs.value.map((l) => [
    l.id,
    `"${l.created_at || ''}"`,
    l.user_id,
    `"${l.provider}"`,
    l.char_len,
    l.latency_ms,
    l.status,
    `"${(l.policy_hits || []).join('; ')}"`,
  ])
  const csvContent = 'data:text/csv;charset=utf-8,' + [headers.join(','), ...rows.map((e) => e.join(','))].join('\n')
  const encodedUri = encodeURI(csvContent)
  const link = document.createElement('a')
  link.setAttribute('href', encodedUri)
  let filename = `opstranslate_audit_logs_${new Date().toISOString().slice(0, 10)}.csv`
  if (logsStore.dateRange && logsStore.dateRange.length === 2) {
    const d1 = new Date(logsStore.dateRange[0]).toISOString().slice(0, 10)
    const d2 = new Date(logsStore.dateRange[1]).toISOString().slice(0, 10)
    filename = `opstranslate_audit_logs_${d1}_to_${d2}.csv`
  }
  link.setAttribute('download', filename)
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
}

const columns = [
  {
    title: 'Timestamp',
    key: 'created_at',
    width: 170,
    render(row: UsageLogItem) {
      return h('span', { class: 'text-xs text-gray-400 font-mono' }, row.created_at || '—')
    },
  },
  {
    title: 'User ID',
    key: 'user_id',
    width: 140,
    render(row: UsageLogItem) {
      return h('span', { class: 'font-mono text-xs font-semibold text-gray-200' }, row.user_id)
    },
  },
  {
    title: 'Provider',
    key: 'provider',
    render(row: UsageLogItem) {
      const p = row.provider || 'Gemini'
      const isCache = p.toLowerCase() === 'cache'
      return h(
        NTag,
        {
          size: 'small',
          bordered: false,
          type: isCache ? 'warning' : 'info',
          class: 'font-mono text-xs font-semibold',
        },
        { default: () => p }
      )
    },
  },
  {
    title: 'Characters',
    key: 'char_len',
    width: 110,
    render(row: UsageLogItem) {
      return h('span', { class: 'text-xs text-gray-400 font-mono' }, `${row.char_len} chars`)
    },
  },
  {
    title: 'Latency',
    key: 'latency_ms',
    width: 120,
    render(row: UsageLogItem) {
      const ms = row.latency_ms
      const type = ms < 2000 ? 'success' : ms < 10000 ? 'info' : ms < 20000 ? 'warning' : 'error'
      return h(
        NTag,
        { size: 'small', type, class: 'font-mono text-xs' },
        { default: () => `${ms} ms` }
      )
    },
  },
  {
    title: 'Status',
    key: 'status',
    width: 110,
    render(row: UsageLogItem) {
      const isOk = row.status === 200 || row.status === 'ok' || String(row.status) === '200'
      return h(
        NTag,
        {
          size: 'small',
          type: isOk ? 'success' : 'error',
          class: 'font-mono text-[11px] font-semibold',
        },
        { default: () => (isOk ? '200 OK' : String(row.status)) }
      )
    },
  },
  {
    title: 'Policy Hits',
    key: 'policy_hits',
    render(row: UsageLogItem) {
      if (!row.policy_hits || row.policy_hits.length === 0) {
        return h('span', { class: 'text-xs text-gray-500 font-mono' }, '—')
      }
      return h(
        'div',
        { class: 'flex flex-wrap gap-1' },
        row.policy_hits.map((hName: string) =>
          h(
            NTag,
            { size: 'tiny', type: 'warning', class: 'font-mono text-[10px]' },
            { default: () => hName }
          )
        )
      )
    },
  },
  {
    title: 'Action',
    key: 'action',
    width: 80,
    render(row: UsageLogItem) {
      return h(
        NButton,
        {
          size: 'tiny',
          quaternary: true,
          onClick: () => openDetail(row),
        },
        { default: () => 'Inspect' }
      )
    },
  },
]
</script>

<template>
  <div class="space-y-6 max-w-7xl mx-auto">
    <!-- Header -->
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
      <div>
        <h1 class="text-2xl font-bold text-gray-100 tracking-tight">Audit & Usage Logs</h1>
        <p class="text-xs text-gray-400 mt-0.5">
          Sanitized operational telemetry (metadata only — zero message body stored to protect user privacy).
        </p>
      </div>
      <div class="flex flex-wrap items-center gap-2 sm:gap-3">
        <NButton secondary size="small" @click="exportToCsv" title="Export current filtered view to CSV">
          <template #icon>
            <DownloadOutline />
          </template>
          Export CSV
        </NButton>
        <div class="w-36 sm:w-44">
          <NSelect
            :value="logsStore.limit"
            :options="limitOptions"
            size="small"
            @update:value="handleLimitChange"
          />
        </div>
        <NButton secondary size="small" @click="() => logsStore.fetchLogs()" :loading="logsStore.loading">
          <template #icon>
            <RefreshOutline />
          </template>
          Refresh
        </NButton>
      </div>
    </div>

    <!-- Filters Bar with Date Time Range Picker -->
    <NCard class="glass-panel border-gray-800 rounded-xl" :bordered="false">
      <div class="flex flex-col lg:flex-row items-stretch lg:items-center gap-3">
        <!-- Search Input -->
        <div class="flex-1 min-w-[200px]">
          <NInput
            v-model:value="searchQuery"
            placeholder="Search by Telegram User ID, Provider, or Policy Concept..."
            size="small"
            clearable
          >
            <template #prefix>
              <SearchOutline class="w-4 h-4 text-gray-500 mr-1" />
            </template>
          </NInput>
        </div>

        <!-- Date Time Range Picker (Naive UI) -->
        <div class="w-full lg:w-[350px] xl:w-[380px]">
          <NDatePicker
            :value="logsStore.dateRange"
            type="datetimerange"
            clearable
            size="small"
            :shortcuts="dateShortcuts"
            start-placeholder="Start Date & Time"
            end-placeholder="End Date & Time"
            @update:value="handleDateRangeChange"
          />
        </div>

        <!-- Provider Select -->
        <div class="w-full lg:w-44">
          <NSelect
            :options="providerOptions"
            :value="selectedProvider || 'all'"
            size="small"
            @update:value="handleProviderSelect"
          />
        </div>

        <!-- Reset Button -->
        <div v-if="hasActiveFilters" class="flex items-center">
          <NButton
            quaternary
            size="small"
            type="warning"
            @click="clearAllFilters"
            title="Reset all active search, date, and provider filters"
          >
            <template #icon>
              <CloseCircleOutline />
            </template>
            Reset
          </NButton>
        </div>
      </div>

      <!-- Active Filter Status & Match Summary -->
      <div
        v-if="hasActiveFilters"
        class="mt-3 pt-3 border-t border-gray-800/80 flex flex-wrap items-center justify-between text-xs text-gray-400 gap-2"
      >
        <div class="flex flex-wrap items-center gap-1.5 sm:gap-2">
          <span class="text-gray-500 flex items-center gap-1 font-medium">
            <FilterOutline class="w-3.5 h-3.5 text-cyan-400" />
            Active Filters:
          </span>

          <NTag
            v-if="logsStore.dateRange"
            size="small"
            type="info"
            closable
            @close="() => handleDateRangeChange(null)"
            class="font-mono text-[11px]"
          >
            📅 {{ formatTimestamp(logsStore.dateRange[0]) }} → {{ formatTimestamp(logsStore.dateRange[1]) }}
          </NTag>

          <NTag
            v-if="selectedProvider && selectedProvider !== 'all'"
            size="small"
            type="info"
            closable
            @close="() => handleProviderSelect('all')"
            class="font-mono text-[11px]"
          >
            Provider: {{ selectedProvider }}
          </NTag>

          <NTag
            v-if="searchQuery.trim()"
            size="small"
            type="info"
            closable
            @close="() => (searchQuery = '')"
            class="text-[11px]"
          >
            Search: "{{ searchQuery.trim() }}"
          </NTag>
        </div>

        <div class="font-mono text-[11px] text-gray-400">
          Showing <span class="text-cyan-400 font-bold">{{ filteredLogs.length }}</span> of
          {{ logsStore.logs.length }} logs
        </div>
      </div>
    </NCard>

    <!-- Table -->
    <NCard class="glass-panel border-gray-800 rounded-xl" :bordered="false">
      <NDataTable
        :columns="columns"
        :data="filteredLogs"
        :loading="logsStore.loading"
        :row-key="(row) => row.id"
        :pagination="{ pageSize: 15 }"
        :scroll-x="900"
      />
    </NCard>

    <!-- Detail Drawer -->
    <NDrawer v-model:show="showDetailDrawer" :width="isMobile ? '100%' : 440" placement="right">
      <NDrawerContent title="Telemetry Log Inspector" closable>
        <div v-if="selectedLog" class="space-y-5 text-xs">
          <div class="p-3.5 rounded-xl bg-gray-900/90 border border-gray-800 space-y-2">
            <div class="flex items-center justify-between">
              <span class="text-gray-400">Log ID</span>
              <span class="font-mono text-gray-200">#{{ selectedLog.id }}</span>
            </div>
            <div class="flex items-center justify-between">
              <span class="text-gray-400">Timestamp</span>
              <span class="font-mono text-gray-300">{{ selectedLog.created_at || '—' }}</span>
            </div>
            <div class="flex items-center justify-between">
              <span class="text-gray-400">Telegram User ID</span>
              <span class="font-mono font-semibold text-emerald-400">{{ selectedLog.user_id }}</span>
            </div>
            <div class="flex items-center justify-between">
              <span class="text-gray-400">Response Status</span>
              <NTag size="small" :type="selectedLog.status === 200 ? 'success' : 'error'">
                HTTP {{ selectedLog.status }}
              </NTag>
            </div>
          </div>

          <!-- Provider & Latency Breakdown -->
          <div class="p-3.5 rounded-xl bg-gray-900/90 border border-gray-800 space-y-3">
            <h4 class="font-semibold text-gray-200 text-xs flex items-center space-x-1.5">
              <span>Routing & Latency Telemetry</span>
            </h4>

            <div class="flex items-center justify-between">
              <span class="text-gray-400">Upstream LLM Provider</span>
              <NTag size="small" class="font-mono text-cyan-300">{{ selectedLog.provider }}</NTag>
            </div>

            <div class="flex items-center justify-between">
              <span class="text-gray-400">Total Roundtrip Latency</span>
              <span
                class="font-mono font-bold text-sm"
                :class="selectedLog.latency_ms < 800 ? 'text-emerald-400' : 'text-amber-400'"
              >
                {{ selectedLog.latency_ms }} ms
              </span>
            </div>

            <div class="flex items-center justify-between">
              <span class="text-gray-400">Input Payload Length</span>
              <span class="font-mono text-gray-300">{{ selectedLog.char_len }} characters</span>
            </div>
          </div>

          <!-- Policy Violations & Concept Hits -->
          <div class="p-3.5 rounded-xl bg-gray-900/90 border border-gray-800 space-y-2.5">
            <h4 class="font-semibold text-gray-200 text-xs">Triggered Policy Concepts</h4>
            <div v-if="selectedLog.policy_hits && selectedLog.policy_hits.length" class="flex flex-wrap gap-1.5">
              <NTag
                v-for="c in selectedLog.policy_hits"
                :key="c"
                size="small"
                type="warning"
                class="font-mono text-xs"
              >
                ⟦T:{{ c }}⟧
              </NTag>
            </div>
            <div v-else class="text-gray-500 italic">
              No sensitive terms triggered in this request.
            </div>
          </div>

          <div class="pt-2">
            <NButton
              type="primary"
              block
              secondary
              @click="sendToPlayground(selectedLog.policy_hits ? selectedLog.policy_hits[0] : undefined)"
            >
              <template #icon>
                <FlaskOutline />
              </template>
              Test Similar Flow in Playground
            </NButton>
          </div>
        </div>
      </NDrawerContent>
    </NDrawer>
  </div>
</template>
