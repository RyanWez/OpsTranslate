<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, h } from 'vue'
import { useRouter } from 'vue-router'
import { useLogsStore } from '../stores/logs'
import { usePlaygroundStore } from '../stores/playground'
import {
  NCard,
  NButton,
  NDataTable,
  NTag,
  NSelect,
  NInput,
  NDrawer,
  NDrawerContent,
} from 'naive-ui'
import {
  RefreshOutline,
  SearchOutline,
  DownloadOutline,
  FlaskOutline,
} from '@vicons/ionicons5'
import type { UsageLogItem } from '../types'

const router = useRouter()
const logsStore = useLogsStore()
const playgroundStore = usePlaygroundStore()

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
]

function handleLimitChange(val: number) {
  logsStore.limit = val
  logsStore.fetchLogs()
}

const providerOptions = computed(() => {
  const set = new Set<string>()
  logsStore.logs.forEach((l) => set.add(l.provider))
  const opts = Array.from(set).map((p) => ({ label: p, value: p }))
  return [{ label: 'All Providers', value: 'all' }, ...opts]
})

function handleProviderSelect(val: string) {
  selectedProvider.value = val === 'all' ? null : val
}

const filteredLogs = computed(() => {
  let list: UsageLogItem[] = logsStore.logs
  if (selectedProvider.value) {
    list = list.filter((l: UsageLogItem) => l.provider === selectedProvider.value)
  }
  if (searchQuery.value.trim()) {
    const q = searchQuery.value.trim().toLowerCase()
    list = list.filter(
      (l: UsageLogItem) =>
        String(l.user_id).includes(q) ||
        l.provider.toLowerCase().includes(q) ||
        l.policy_hits.some((p: string) => p.toLowerCase().includes(q))
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
    `"${l.policy_hits.join('; ')}"`,
  ])
  const csvContent = 'data:text/csv;charset=utf-8,' + [headers.join(','), ...rows.map((e) => e.join(','))].join('\n')
  const encodedUri = encodeURI(csvContent)
  const link = document.createElement('a')
  link.setAttribute('href', encodedUri)
  link.setAttribute('download', `opstranslate_audit_logs_${new Date().toISOString().slice(0, 10)}.csv`)
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
      <div class="flex items-center space-x-3">
        <NButton secondary size="small" @click="exportToCsv" title="Export current filtered view to CSV">
          <template #icon>
            <DownloadOutline />
          </template>
          Export CSV
        </NButton>
        <div class="w-40">
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

    <!-- Filters Bar -->
    <NCard class="glass-panel border-gray-800 rounded-xl" :bordered="false">
      <div class="flex flex-wrap items-center gap-4">
        <div class="flex-1 min-w-[240px]">
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

        <div class="w-48">
          <NSelect
            :options="providerOptions"
            :value="selectedProvider || 'all'"
            size="small"
            @update:value="handleProviderSelect"
          />
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
      />
    </NCard>

    <!-- Detail Drawer -->
    <NDrawer v-model:show="showDetailDrawer" :width="440" placement="right">
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
              <span class="font-mono font-bold text-sm" :class="selectedLog.latency_ms < 800 ? 'text-emerald-400' : 'text-amber-400'">
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
            <div v-if="selectedLog.policy_hits.length" class="flex flex-wrap gap-1.5">
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
            <NButton type="primary" block secondary @click="sendToPlayground(selectedLog.policy_hits[0])">
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
