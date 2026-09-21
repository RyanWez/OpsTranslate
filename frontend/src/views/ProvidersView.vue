<script setup lang="ts">
import { ref, onMounted, h } from 'vue'
import { useProvidersStore } from '../stores/providers'
import {
  NCard,
  NButton,
  NDataTable,
  NTag,
  NModal,
  NForm,
  NFormItem,
  NInput,
  NInputNumber,
  NSwitch,
  useMessage,
  useDialog,
  NDrawer,
  NDrawerContent,
} from 'naive-ui'
import {
  AddOutline,
  RefreshOutline,
  FlashOutline,
  CheckmarkCircleOutline,
  CloseCircleOutline,
} from '@vicons/ionicons5'
import type { ProviderItem, ProviderPayload, TestProviderResult } from '../types'

const providersStore = useProvidersStore()
const message = useMessage()
const dialog = useDialog()

onMounted(() => {
  providersStore.fetchProviders()
})

// Modal Add/Edit State
const showModal = ref(false)
const modalTitle = ref('Add AI Provider')
const editingTarget = ref<ProviderItem | null>(null)
const formData = ref<ProviderPayload>({
  name: '',
  base_url: '',
  api_key: '',
  model: '',
  priority: 1,
  enabled: true,
  timeout_s: 15.0,
})

function openAddModal() {
  editingTarget.value = null
  modalTitle.value = 'Add AI Provider'
  formData.value = {
    name: '',
    base_url: 'https://api.openai.com/v1',
    api_key: '',
    model: 'gpt-4o-mini',
    priority: 1,
    enabled: true,
    timeout_s: 15.0,
  }
  showModal.value = true
}

function openEditModal(row: ProviderItem) {
  editingTarget.value = row
  modalTitle.value = `Edit Provider: ${row.name}`
  formData.value = {
    name: row.name,
    base_url: row.base_url,
    api_key: '',
    model: row.model,
    priority: row.priority,
    enabled: row.enabled,
    timeout_s: row.timeout_s,
  }
  showModal.value = true
}

async function handleSaveProvider() {
  if (!formData.value.name || !formData.value.base_url || !formData.value.model) {
    message.warning('Please fill in all required fields')
    return
  }

  try {
    const targetId = editingTarget.value ? (editingTarget.value.id ?? editingTarget.value.name) : null
    const success = await providersStore.saveProvider(targetId, formData.value)
    if (success) {
      message.success(editingTarget.value ? 'Provider updated' : 'Provider created')
      showModal.value = false
    }
  } catch (err: any) {
    message.error(err.response?.data?.detail || 'Failed to save provider')
  }
}

function handleDeleteProvider(row: ProviderItem) {
  dialog.warning({
    title: 'Confirm Deletion',
    content: `Are you sure you want to delete provider '${row.name}'?`,
    positiveText: 'Delete',
    negativeText: 'Cancel',
    onPositiveClick: async () => {
      try {
        const targetId = row.id !== null ? row.id : row.name
        await providersStore.deleteProvider(targetId)
        message.success(`Provider '${row.name}' deleted`)
      } catch (err: any) {
        message.error(err.response?.data?.detail || 'Failed to delete provider')
      }
    },
  })
}

// Test Connection Drawer
const showTestDrawer = ref(false)
const testingTarget = ref<ProviderItem | null>(null)
const customTestKey = ref('')
const testResult = ref<TestProviderResult | null>(null)
const isTesting = ref(false)

async function openTestDrawer(row: ProviderItem) {
  testingTarget.value = row
  customTestKey.value = ''
  testResult.value = null
  showTestDrawer.value = true
}

async function runPingTest() {
  if (!testingTarget.value) return
  isTesting.value = true
  testResult.value = null

  try {
    const res = await providersStore.testProviderConnection({
      base_url: testingTarget.value.base_url,
      api_key: customTestKey.value || '',
      model: testingTarget.value.model,
      timeout_s: testingTarget.value.timeout_s,
    })
    testResult.value = res
  } finally {
    isTesting.value = false
  }
}

// Table columns
const columns = [
  {
    title: 'Priority',
    key: 'priority',
    width: 90,
    render(row: ProviderItem) {
      return h(
        NTag,
        {
          type: row.priority === 1 ? 'success' : 'info',
          size: 'small',
          class: 'font-mono text-[11px]',
        },
        { default: () => `P${row.priority}` }
      )
    },
  },
  {
    title: 'Identifier & Model',
    key: 'name',
    render(row: ProviderItem) {
      return h('div', { class: 'space-y-0.5' }, [
        h('div', { class: 'flex items-center space-x-2' }, [
          h('span', { class: 'font-semibold text-gray-200' }, row.name),
          h(
            NTag,
            { size: 'small', bordered: false, class: 'text-[10px] text-gray-400' },
            { default: () => row.source }
          ),
        ]),
        h('div', { class: 'text-xs text-gray-400 font-mono' }, row.model),
      ])
    },
  },
  {
    title: 'Base URL',
    key: 'base_url',
    ellipsis: true,
    render(row: ProviderItem) {
      return h('span', { class: 'font-mono text-xs text-gray-300' }, row.base_url)
    },
  },
  {
    title: 'Circuit Breaker',
    key: 'breaker_state',
    width: 140,
    render(row: ProviderItem) {
      const type =
        row.breaker_state === 'closed'
          ? 'success'
          : row.breaker_state === 'half-open'
          ? 'warning'
          : 'error'
      return h(
        NTag,
        { type, size: 'small', class: 'uppercase text-[11px] font-mono' },
        { default: () => row.breaker_state }
      )
    },
  },
  {
    title: 'Timeout',
    key: 'timeout_s',
    width: 90,
    render(row: ProviderItem) {
      return h('span', { class: 'text-xs text-gray-400 font-mono' }, `${row.timeout_s}s`)
    },
  },
  {
    title: 'Actions',
    key: 'actions',
    width: 210,
    render(row: ProviderItem) {
      return h('div', { class: 'flex items-center space-x-2' }, [
        h(
          NButton,
          {
            size: 'tiny',
            secondary: true,
            type: 'info',
            onClick: () => openTestDrawer(row),
          },
          { default: () => 'Ping Test' }
        ),
        h(
          NButton,
          {
            size: 'tiny',
            secondary: true,
            onClick: () => openEditModal(row),
          },
          { default: () => 'Edit' }
        ),
        h(
          NButton,
          {
            size: 'tiny',
            quaternary: true,
            type: 'error',
            onClick: () => handleDeleteProvider(row),
          },
          { default: () => 'Delete' }
        ),
      ])
    },
  },
]
</script>

<template>
  <div class="space-y-6 max-w-7xl mx-auto">
    <!-- Header -->
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
      <div>
        <h1 class="text-2xl font-bold text-gray-100 tracking-tight">AI Providers Gateway</h1>
        <p class="text-xs text-gray-400 mt-0.5">Manage upstream LLMs, fallback priority order, timeout budgets, and live health pings.</p>
      </div>
      <div class="flex items-center space-x-3">
        <NButton secondary size="small" @click="providersStore.fetchProviders" :loading="providersStore.loading">
          <template #icon>
            <RefreshOutline />
          </template>
          Refresh
        </NButton>
        <NButton type="primary" size="small" @click="openAddModal">
          <template #icon>
            <AddOutline />
          </template>
          Add Provider
        </NButton>
      </div>
    </div>

    <!-- Provider Table Card -->
    <NCard class="glass-panel border-gray-800 rounded-xl" :bordered="false">
      <NDataTable
        :columns="columns"
        :data="providersStore.providers"
        :loading="providersStore.loading"
        :row-key="(row) => row.name"
      />
    </NCard>

    <!-- Add / Edit Modal -->
    <NModal v-model:show="showModal" preset="card" :title="modalTitle" class="max-w-lg glass-panel border-gray-800 rounded-xl">
      <NForm label-placement="top" class="space-y-4">
        <div class="grid grid-cols-2 gap-4">
          <NFormItem label="Provider Identifier" required>
            <NInput v-model:value="formData.name" placeholder="e.g. openai-primary" />
          </NFormItem>
          <NFormItem label="Failover Priority (1 = Primary)" required>
            <NInputNumber v-model:value="formData.priority" :min="1" :max="100" class="w-full" />
          </NFormItem>
        </div>

        <NFormItem label="Base URL (OpenAI-compatible)" required>
          <NInput v-model:value="formData.base_url" placeholder="https://api.openai.com/v1" />
        </NFormItem>

        <div class="grid grid-cols-2 gap-4">
          <NFormItem label="Model ID" required>
            <NInput v-model:value="formData.model" placeholder="e.g. gpt-4o-mini" />
          </NFormItem>
          <NFormItem label="Timeout (seconds)">
            <NInputNumber v-model:value="formData.timeout_s" :min="1" :max="120" :step="0.5" class="w-full" />
          </NFormItem>
        </div>

        <NFormItem label="API Key">
          <NInput
            v-model:value="formData.api_key"
            type="password"
            show-password-on="click"
            placeholder="Leave empty when editing to preserve current key"
          />
        </NFormItem>

        <div class="flex items-center justify-between pt-2">
          <span class="text-xs text-gray-300">Enable Provider in Router</span>
          <NSwitch v-model:value="formData.enabled" />
        </div>

        <div class="flex justify-end space-x-3 pt-4 border-t border-gray-800/80">
          <NButton @click="showModal = false">Cancel</NButton>
          <NButton type="primary" :loading="providersStore.loading" @click="handleSaveProvider">Save Provider</NButton>
        </div>
      </NForm>
    </NModal>

    <!-- Ping Test Drawer -->
    <NDrawer v-model:show="showTestDrawer" :width="460" placement="right">
      <NDrawerContent :title="`Test Connection: ${testingTarget?.name || ''}`" closable>
        <div class="space-y-4">
          <div class="p-3 rounded-lg bg-gray-900/80 border border-gray-800 text-xs space-y-1 font-mono">
            <div><span class="text-gray-500">Base URL:</span> {{ testingTarget?.base_url }}</div>
            <div><span class="text-gray-500">Model:</span> {{ testingTarget?.model }}</div>
            <div><span class="text-gray-500">Masked Key:</span> {{ testingTarget?.api_key_masked || 'None' }}</div>
          </div>

          <div class="space-y-1.5">
            <label class="text-xs text-gray-300">API Key (if testing new key or unpersisted)</label>
            <NInput
              v-model:value="customTestKey"
              type="password"
              show-password-on="click"
              placeholder="Paste key to test, or leave blank to test DB key"
            />
          </div>

          <NButton type="primary" block :loading="isTesting" @click="runPingTest">
            <template #icon>
              <FlashOutline />
            </template>
            Execute Live Ping & Translation Test
          </NButton>

          <!-- Result Preview -->
          <div v-if="testResult" class="mt-4 p-4 rounded-xl border space-y-3" :class="testResult.ok ? 'bg-emerald-950/20 border-emerald-800/50' : 'bg-red-950/20 border-red-800/50'">
            <div class="flex items-center justify-between">
              <div class="flex items-center space-x-2">
                <CheckmarkCircleOutline v-if="testResult.ok" class="w-5 h-5 text-emerald-400" />
                <CloseCircleOutline v-else class="w-5 h-5 text-red-400" />
                <span class="font-bold text-sm" :class="testResult.ok ? 'text-emerald-400' : 'text-red-400'">
                  {{ testResult.ok ? 'Connection Successful' : 'Connection Failed' }}
                </span>
              </div>
              <NTag size="small" :type="testResult.ok ? 'success' : 'error'" class="font-mono text-xs">
                {{ testResult.latency_ms }} ms
              </NTag>
            </div>

            <div v-if="testResult.sample_output" class="text-xs space-y-1">
              <span class="text-gray-400">Sample Completion ('Hello' -> Myanmar):</span>
              <div class="p-2.5 rounded bg-black/40 font-mono text-emerald-300">
                {{ testResult.sample_output }}
              </div>
            </div>

            <div v-if="testResult.error" class="text-xs space-y-1">
              <span class="text-gray-400">Error Detail:</span>
              <div class="p-2.5 rounded bg-black/40 font-mono text-red-300 break-words">
                {{ testResult.error }}
              </div>
            </div>
          </div>
        </div>
      </NDrawerContent>
    </NDrawer>
  </div>
</template>
