<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import {
  NCard,
  NButton,
  NInput,
  NTag,
  NAlert,
  NSpin,
  useMessage,
  useDialog,
} from 'naive-ui'
import {
  RefreshOutline,
  CloudUploadOutline,
  PaperPlaneOutline,
  SparklesOutline,
  ReloadOutline,
} from '@vicons/ionicons5'
import { api } from '../api'

interface EmojiSlotItem {
  key: string
  label: string
  category: string
  fallback: string
  custom_emoji_id: string
  description: string
  tag_preview?: string
}

const message = useMessage()
const dialog = useDialog()

const loading = ref(false)
const saving = ref(false)
const testing = ref(false)
const slots = ref<EmojiSlotItem[]>([])

const pipelineSlots = computed(() => slots.value.filter(s => s.category === 'Pipeline'))
const commandSlots = computed(() => slots.value.filter(s => s.category === 'Commands'))
const alertSlots = computed(() => slots.value.filter(s => s.category === 'Alerts'))

async function fetchSlots() {
  loading.value = true
  try {
    const res = await api.getBotEmojis()
    if (res.data?.slots) {
      slots.value = res.data.slots
    }
  } catch (err: any) {
    message.error('Failed to load animated emoji slots: ' + (err.response?.data?.detail || err.message))
  } finally {
    loading.value = false
  }
}

async function saveSlots() {
  saving.value = true
  try {
    const payload = slots.value.map(s => ({
      key: s.key,
      custom_emoji_id: (s.custom_emoji_id || '').trim(),
      fallback: (s.fallback || '').trim(),
    }))
    const res = await api.updateBotEmojis(payload)
    if (res.data?.ok) {
      message.success('Telegram Animated Emoji Set updated successfully!')
      slots.value = res.data.slots
    }
  } catch (err: any) {
    message.error('Save failed: ' + (err.response?.data?.detail || err.message))
  } finally {
    saving.value = false
  }
}

async function sendTestMessage() {
  testing.value = true
  try {
    const res = await api.testBotEmojis()
    if (res.data?.ok) {
      message.success(`Preview message sent to Admin Telegram Chat (ID: ${res.data.message_id || 'OK'})!`)
    }
  } catch (err: any) {
    message.error('Test send failed: ' + (err.response?.data?.detail || err.message))
  } finally {
    testing.value = false
  }
}

function resetDefaults() {
  dialog.info({
    title: 'Reset Emoji Set',
    content: 'Clear all custom animated emoji IDs and revert to standard Unicode fallbacks?',
    positiveText: 'Reset',
    negativeText: 'Cancel',
    onPositiveClick: () => {
      for (const slot of slots.value) {
        slot.custom_emoji_id = ''
      }
      message.info('Cleared custom emoji IDs. Click "Save & Apply" to commit changes.')
    },
  })
}

function previewTag(slot: EmojiSlotItem): string {
  const id = (slot.custom_emoji_id || '').trim()
  if (id && /^\d+$/.test(id)) {
    return `<tg-emoji emoji-id="${id}">${slot.fallback}</tg-emoji>`
  }
  return slot.fallback
}

onMounted(() => {
  fetchSlots()
})
</script>

<template>
  <div class="space-y-6 max-w-5xl mx-auto pb-12">
    <!-- Header -->
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
      <div>
        <h1 class="text-xl font-bold text-gray-100 flex items-center gap-2">
          <SparklesOutline class="w-6 h-6 text-emerald-400" />
          <span>Telegram Animated Emoji Set</span>
        </h1>
        <p class="text-xs text-gray-400 mt-1">
          Configure custom animated emoji IDs (Telegram Premium) for translation loading, headers, direction arrows, and bot commands.
        </p>
      </div>

      <div class="flex items-center gap-2 flex-wrap">
        <NButton secondary size="small" :loading="loading" @click="fetchSlots">
          <template #icon><RefreshOutline /></template>
          Refresh
        </NButton>
        <NButton secondary size="small" @click="resetDefaults">
          <template #icon><ReloadOutline /></template>
          Reset
        </NButton>
        <NButton secondary type="info" size="small" :loading="testing" @click="sendTestMessage">
          <template #icon><PaperPlaneOutline /></template>
          Send Test to Telegram
        </NButton>
        <NButton type="primary" size="small" :loading="saving" @click="saveSlots">
          <template #icon><CloudUploadOutline /></template>
          Save & Apply
        </NButton>
      </div>
    </div>

    <!-- Info banner -->
    <NAlert type="info" :bordered="false" class="bg-cyan-950/30 border border-cyan-900/40">
      <div class="text-xs text-cyan-200/90 leading-relaxed space-y-1">
        <div><strong>💡 How Custom Emojis Work:</strong> Enter the numeric Telegram <code>custom_emoji_id</code> from any Telegram Premium emoji pack.</div>
        <div><strong>Finding IDs:</strong> Send any custom animated emoji to your bot or to <code>@getidsbot</code> to view its unique document ID.</div>
        <div><strong>Fallback Guarantee:</strong> If a custom emoji ID is empty or invalid, the bot will gracefully render the standard fallback emoji.</div>
      </div>
    </NAlert>

    <NSpin :show="loading">
      <div class="space-y-6">
        <!-- 1. Translation Pipeline -->
        <NCard size="small" class="border border-gray-800 bg-gray-900/40 backdrop-blur">
          <template #header>
            <div class="flex items-center gap-2 text-sm font-semibold text-emerald-400">
              <span>⚡ Translation Pipeline Emojis</span>
            </div>
          </template>

          <div class="divide-y divide-gray-800/80">
            <div
              v-for="slot in pipelineSlots"
              :key="slot.key"
              class="py-3 flex flex-col md:flex-row md:items-center justify-between gap-3"
            >
              <div class="md:w-1/3">
                <div class="flex items-center gap-2">
                  <span class="text-base">{{ slot.fallback }}</span>
                  <span class="text-xs font-semibold text-gray-200">{{ slot.label }}</span>
                </div>
                <div class="text-[11px] text-gray-400 mt-0.5">{{ slot.description }}</div>
              </div>

              <div class="flex items-center gap-3 flex-1">
                <div class="w-16">
                  <NInput
                    v-model:value="slot.fallback"
                    size="small"
                    placeholder="Fallback"
                    class="text-center font-mono text-xs"
                  />
                </div>
                <div class="flex-1">
                  <NInput
                    v-model:value="slot.custom_emoji_id"
                    size="small"
                    placeholder="Custom Emoji ID (e.g. 5368324170671202286)"
                    class="font-mono text-xs"
                    clearable
                  />
                </div>
              </div>

              <div class="md:w-44 text-right">
                <NTag size="small" :bordered="false" :type="slot.custom_emoji_id ? 'success' : 'default'">
                  <span class="font-mono text-[11px] truncate max-w-[150px] inline-block">
                    {{ previewTag(slot) }}
                  </span>
                </NTag>
              </div>
            </div>
          </div>
        </NCard>

        <!-- 2. Bot Commands -->
        <NCard size="small" class="border border-gray-800 bg-gray-900/40 backdrop-blur">
          <template #header>
            <div class="flex items-center gap-2 text-sm font-semibold text-cyan-400">
              <span>💬 Bot Command Response Emojis</span>
            </div>
          </template>

          <div class="divide-y divide-gray-800/80">
            <div
              v-for="slot in commandSlots"
              :key="slot.key"
              class="py-3 flex flex-col md:flex-row md:items-center justify-between gap-3"
            >
              <div class="md:w-1/3">
                <div class="flex items-center gap-2">
                  <span class="text-base">{{ slot.fallback }}</span>
                  <span class="text-xs font-semibold text-gray-200">{{ slot.label }}</span>
                </div>
                <div class="text-[11px] text-gray-400 mt-0.5">{{ slot.description }}</div>
              </div>

              <div class="flex items-center gap-3 flex-1">
                <div class="w-16">
                  <NInput
                    v-model:value="slot.fallback"
                    size="small"
                    placeholder="Fallback"
                    class="text-center font-mono text-xs"
                  />
                </div>
                <div class="flex-1">
                  <NInput
                    v-model:value="slot.custom_emoji_id"
                    size="small"
                    placeholder="Custom Emoji ID (e.g. 5368324170671202286)"
                    class="font-mono text-xs"
                    clearable
                  />
                </div>
              </div>

              <div class="md:w-44 text-right">
                <NTag size="small" :bordered="false" :type="slot.custom_emoji_id ? 'success' : 'default'">
                  <span class="font-mono text-[11px] truncate max-w-[150px] inline-block">
                    {{ previewTag(slot) }}
                  </span>
                </NTag>
              </div>
            </div>
          </div>
        </NCard>

        <!-- 3. System Alerts & Warnings -->
        <NCard size="small" class="border border-gray-800 bg-gray-900/40 backdrop-blur">
          <template #header>
            <div class="flex items-center gap-2 text-sm font-semibold text-amber-400">
              <span>⚠️ System Alerts & Warnings Emojis</span>
            </div>
          </template>

          <div class="divide-y divide-gray-800/80">
            <div
              v-for="slot in alertSlots"
              :key="slot.key"
              class="py-3 flex flex-col md:flex-row md:items-center justify-between gap-3"
            >
              <div class="md:w-1/3">
                <div class="flex items-center gap-2">
                  <span class="text-base">{{ slot.fallback }}</span>
                  <span class="text-xs font-semibold text-gray-200">{{ slot.label }}</span>
                </div>
                <div class="text-[11px] text-gray-400 mt-0.5">{{ slot.description }}</div>
              </div>

              <div class="flex items-center gap-3 flex-1">
                <div class="w-16">
                  <NInput
                    v-model:value="slot.fallback"
                    size="small"
                    placeholder="Fallback"
                    class="text-center font-mono text-xs"
                  />
                </div>
                <div class="flex-1">
                  <NInput
                    v-model:value="slot.custom_emoji_id"
                    size="small"
                    placeholder="Custom Emoji ID (e.g. 5368324170671202286)"
                    class="font-mono text-xs"
                    clearable
                  />
                </div>
              </div>

              <div class="md:w-44 text-right">
                <NTag size="small" :bordered="false" :type="slot.custom_emoji_id ? 'success' : 'default'">
                  <span class="font-mono text-[11px] truncate max-w-[150px] inline-block">
                    {{ previewTag(slot) }}
                  </span>
                </NTag>
              </div>
            </div>
          </div>
        </NCard>
      </div>
    </NSpin>
  </div>
</template>
