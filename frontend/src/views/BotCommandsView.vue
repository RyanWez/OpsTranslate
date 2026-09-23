<script setup lang="ts">
import { ref, onMounted, h } from 'vue'
import {
  NCard,
  NButton,
  NDataTable,
  NInput,
  NModal,
  NForm,
  NFormItem,
  NTag,
  NAlert,
  useMessage,
  useDialog,
} from 'naive-ui'
import {
  AddOutline,
  RefreshOutline,
  CloudUploadOutline,
  TrashOutline,
  CreateOutline,
} from '@vicons/ionicons5'
import { api } from '../api'

interface BotCommandItem {
  command: string
  description: string
}

const message = useMessage()
const dialog = useDialog()

const loading = ref(false)
const syncing = ref(false)
const commands = ref<BotCommandItem[]>([])

const showModal = ref(false)
const isEditing = ref(false)
const editIndex = ref(-1)
const formData = ref<BotCommandItem>({
  command: '',
  description: '',
})

const DEFAULT_COMMANDS: BotCommandItem[] = [
  { command: 'start', description: '🚀 Set up / change target language' },
  { command: 'tr', description: '🌐 Translate a replied-to message' },
  { command: 'help', description: '📖 How to use this bot' },
  { command: 'status', description: '📊 Bot and provider status' },
  { command: 'report', description: '🚩 Flag translation for review' },
  { command: 'whoami', description: '🆔 Check your Telegram user ID' },
]

const EMOJI_PRESETS = ['🚀', '🌐', '📖', '📊', '🚩', '🆔', '⚙️', '💬', '✨', '🇲🇲', '🇬🇧', '🔒']

async function fetchCommands() {
  loading.value = true
  try {
    const res = await api.getBotCommands()
    if (res.data?.commands && res.data.commands.length > 0) {
      commands.value = [...res.data.commands]
    } else {
      commands.value = [...DEFAULT_COMMANDS]
    }
  } catch (err: any) {
    message.error('Failed to load bot commands: ' + (err.response?.data?.detail || err.message))
    commands.value = [...DEFAULT_COMMANDS]
  } finally {
    loading.value = false
  }
}

async function syncToTelegram() {
  syncing.value = true
  try {
    const payload = commands.value.map(c => ({
      command: c.command.trim().replace(/^\//, '').toLowerCase(),
      description: c.description.trim(),
    }))
    const res = await api.updateBotCommands(payload)
    if (res.data?.ok) {
      message.success('Telegram Bot menu commands synced live successfully!')
      commands.value = res.data.commands
    }
  } catch (err: any) {
    message.error('Sync failed: ' + (err.response?.data?.detail || err.message))
  } finally {
    syncing.value = false
  }
}

function openAddModal() {
  isEditing.value = false
  editIndex.value = -1
  formData.value = { command: '', description: '' }
  showModal.value = true
}

function openEditModal(index: number) {
  isEditing.value = true
  editIndex.value = index
  formData.value = { ...commands.value[index] }
  showModal.value = true
}

function deleteCommand(index: number) {
  const cmd = commands.value[index]
  dialog.warning({
    title: 'Confirm Delete',
    content: `Are you sure you want to delete /${cmd.command}?`,
    positiveText: 'Delete',
    negativeText: 'Cancel',
    onPositiveClick: () => {
      commands.value.splice(index, 1)
      message.info(`Removed /${cmd.command}. Click 'Save & Sync' to apply on Telegram.`)
    },
  })
}

function saveModalForm() {
  const cmd = formData.value.command.trim().replace(/^\//, '').toLowerCase()
  const desc = formData.value.description.trim()

  if (!cmd) {
    message.warning('Command name (e.g. start) is required')
    return
  }
  if (!desc) {
    message.warning('Description is required')
    return
  }

  if (isEditing.value && editIndex.value >= 0) {
    commands.value[editIndex.value] = { command: cmd, description: desc }
  } else {
    if (commands.value.some(c => c.command.toLowerCase() === cmd)) {
      message.warning(`/${cmd} already exists in the commands list`)
      return
    }
    commands.value.push({ command: cmd, description: desc })
  }
  showModal.value = false
}

function resetToDefaults() {
  dialog.info({
    title: 'Reset to Defaults',
    content: 'Reset command list back to standard English commands?',
    positiveText: 'Reset',
    negativeText: 'Cancel',
    onPositiveClick: () => {
      commands.value = JSON.parse(JSON.stringify(DEFAULT_COMMANDS))
      message.success('Reset to standard English defaults. Click "Save & Sync" to push to Telegram.')
    },
  })
}

function appendEmoji(emoji: string) {
  formData.value.description = `${emoji} ${formData.value.description}`.trim()
}

const columns = [
  {
    title: 'Command',
    key: 'command',
    width: 140,
    render: (row: BotCommandItem) =>
      h(NTag, { type: 'info', bordered: false, class: 'font-mono font-semibold' }, { default: () => `/${row.command}` }),
  },
  {
    title: 'Description & Emoji',
    key: 'description',
    render: (row: BotCommandItem) => h('span', { class: 'text-gray-200 text-sm' }, row.description),
  },
  {
    title: 'Actions',
    key: 'actions',
    width: 120,
    render: (_row: BotCommandItem, index: number) =>
      h('div', { class: 'flex items-center gap-1.5' }, [
        h(
          NButton,
          { size: 'tiny', secondary: true, onClick: () => openEditModal(index) },
          { default: () => h(CreateOutline, { class: 'w-3.5 h-3.5' }) }
        ),
        h(
          NButton,
          { size: 'tiny', secondary: true, type: 'error', onClick: () => deleteCommand(index) },
          { default: () => h(TrashOutline, { class: 'w-3.5 h-3.5' }) }
        ),
      ]),
  },
]

onMounted(() => {
  fetchCommands()
})
</script>

<template>
  <div class="space-y-5 max-w-5xl mx-auto">
    <!-- Header -->
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
      <div>
        <h1 class="text-xl font-bold text-gray-100 flex items-center gap-2">
          <span>🤖 Telegram Bot Commands & Emojis</span>
        </h1>
        <p class="text-xs text-gray-400 mt-1">
          Manage menu commands, descriptions, and emojis displayed in the Telegram bot menu button without using @BotFather.
        </p>
      </div>

      <div class="flex items-center gap-2">
        <NButton secondary size="small" :loading="loading" @click="fetchCommands">
          <template #icon><NIcon><RefreshOutline /></NIcon></template>
          Refresh
        </NButton>
        <NButton secondary size="small" @click="resetToDefaults">
          Defaults
        </NButton>
        <NButton type="primary" size="small" :loading="syncing" @click="syncToTelegram">
          <template #icon><NIcon><CloudUploadOutline /></NIcon></template>
          Save & Sync to Telegram
        </NButton>
      </div>
    </div>

    <!-- Alert / Notice banner -->
    <NAlert type="info" :bordered="false" class="bg-cyan-950/30 border border-cyan-900/40">
      <div class="text-xs text-cyan-200/90 leading-relaxed">
        <strong>💡 Real-time Sync:</strong> Changes are saved to database and synced directly to Telegram Bot API when you click <strong>"Save & Sync to Telegram"</strong> without requiring any server restarts.
      </div>
    </NAlert>

    <!-- Table Card -->
    <NCard size="small" class="border border-gray-800 bg-gray-900/40 backdrop-blur">
      <div class="flex items-center justify-between mb-3 px-1">
        <div class="text-xs font-semibold text-gray-300 uppercase tracking-wider">
          Active Commands ({{ commands.length }})
        </div>
        <NButton size="tiny" type="primary" secondary @click="openAddModal">
          <template #icon><NIcon><AddOutline /></NIcon></template>
          Add Command
        </NButton>
      </div>

      <NDataTable
        :columns="columns"
        :data="commands"
        :loading="loading"
        :bordered="false"
        size="small"
        :row-key="(row: BotCommandItem) => row.command"
      />
    </NCard>

    <!-- Add / Edit Modal -->
    <NModal
      v-model:show="showModal"
      preset="card"
      :title="isEditing ? 'Edit Command' : 'Add Command'"
      class="max-w-md bg-[#111827] border border-gray-800"
    >
      <NForm label-placement="top" size="small">
        <NFormItem label="Command Name">
          <NInput
            v-model:value="formData.command"
            placeholder="e.g. start, tr, help"
            :disabled="isEditing"
          >
            <template #prefix>/</template>
          </NInput>
        </NFormItem>

        <NFormItem label="Description & Emoji">
          <div class="w-full space-y-2">
            <NInput
              v-model:value="formData.description"
              placeholder="e.g. 🚀 Set up / change target language"
            />
            <div class="flex items-center gap-1.5 flex-wrap pt-1">
              <span class="text-[11px] text-gray-400">Quick Emojis:</span>
              <button
                v-for="e in EMOJI_PRESETS"
                :key="e"
                type="button"
                class="px-1.5 py-0.5 text-xs bg-gray-800 hover:bg-gray-700 text-gray-200 rounded border border-gray-700 transition"
                @click="appendEmoji(e)"
              >
                {{ e }}
              </button>
            </div>
          </div>
        </NFormItem>

        <div class="flex justify-end gap-2 mt-4">
          <NButton size="small" secondary @click="showModal = false">Cancel</NButton>
          <NButton size="small" type="primary" @click="saveModalForm">Save</NButton>
        </div>
      </NForm>
    </NModal>
  </div>
</template>
