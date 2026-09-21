<script setup lang="ts">
import { ref, onMounted, computed, h } from 'vue'
import { useLogsStore } from '../stores/logs'
import {
  NCard,
  NButton,
  NDataTable,
  NTag,
  NSelect,
  NInput,
} from 'naive-ui'
import { RefreshOutline, SearchOutline } from '@vicons/ionicons5'
import type { UsageLogItem } from '../types'

const logsStore = useLogsStore()

onMounted(() => {
  logsStore.fetchLogs()
})

const searchQuery = ref('')
const selectedProvider = ref<string | null>(null)

const limitOptions = [
  { label: 'Latest 50 logs', value: 50 },
  { label: 'Latest 100 logs', value: 100 },
  { label: 'Latest 200 logs', value: 200 },
]

function handleLimitChange(val: number) {
  logsStore.limit = val
  logsStore.fetchLogs()
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
      return h(
        NTag,
        { size: 'small', bordered: false, class: 'font-mono text-xs text-cyan-300' },
        { default: () => row.provider }
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
      const type = ms < 800 ? 'success' : ms < 2500 ? 'warning' : 'error'
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
    width: 100,
    render(row: UsageLogItem) {
      return h(
        NTag,
        {
          size: 'small',
          type: row.status === 200 ? 'success' : 'error',
          class: 'font-mono text-[11px]',
        },
        { default: () => row.status }
      )
    },
  },
  {
    title: 'Policy Hits',
    key: 'policy_hits',
    render(row: UsageLogItem) {
      if (!row.policy_hits || row.policy_hits.length === 0) {
        return h('span', { class: 'text-xs text-gray-600' }, 'None')
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
]
</script>

<template>
  <div class="space-y-6 max-w-7xl mx-auto">
    <!-- Header -->
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
      <div>
        <h1 class="text-2xl font-bold text-gray-100 tracking-tight">Audit & Usage Logs</h1>
        <p class="text-xs text-gray-400 mt-0.5">Sanitized operational telemetry (metadata only — zero message body logged).</p>
      </div>
      <div class="flex items-center space-x-3">
        <div class="w-44">
          <NSelect
            :value="logsStore.limit"
            :options="limitOptions"
            size="small"
            @update:value="handleLimitChange"
          />
        </div>
        <NButton secondary size="small" @click="logsStore.fetchLogs" :loading="logsStore.loading">
          <template #icon>
            <RefreshOutline />
          </template>
          Refresh
        </NButton>
      </div>
    </div>

    <!-- Filters -->
    <NCard class="glass-panel border-gray-800 rounded-xl" :bordered="false">
      <div class="flex flex-wrap items-center gap-4">
        <div class="flex-1 min-w-[200px]">
          <NInput
            v-model:value="searchQuery"
            placeholder="Search by User ID, Provider, or Policy Hit..."
            size="small"
            clearable
          >
            <template #prefix>
              <SearchOutline class="w-4 h-4 text-gray-500 mr-1" />
            </template>
          </NInput>
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
  </div>
</template>
