<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import {
  NCard, NButton, NSwitch, NInput, NAlert, NSpin, NTag,
  NCheckbox, useMessage, useDialog,
} from 'naive-ui'
import {
  ConstructOutline, SaveOutline, RefreshOutline, EyeOutline,
  WarningOutline, CheckmarkCircleOutline, ReloadOutline,
} from '@vicons/ionicons5'
import { apiClient } from '../api/client'

const message = useMessage()
const dialog = useDialog()

const loading = ref(false)
const saving = ref(false)

// Form state
const enabled = ref(false)
const title = ref('')
const msgText = ref('')
const resumedMsgText = ref('')
const allowAdminBypass = ref(false)
const notifyStaff = ref(true)

// Defaults from server
const defaultMessage = ref('')
const defaultResumedMessage = ref('')
const defaultTitle = ref('')
const updatedAt = ref<string | null>(null)

// Validation
const titleError = computed(() => {
  if (title.value.length > 120) return 'Title must be ≤ 120 characters'
  return ''
})
const messageError = computed(() => {
  if (msgText.value.length > 4000) return 'Message must be ≤ 4000 characters'
  return ''
})
const resumedMessageError = computed(() => {
  if (resumedMsgText.value.length > 4000) return 'Resumed message must be ≤ 4000 characters'
  return ''
})
const canSave = computed(() => !titleError.value && !messageError.value && !resumedMessageError.value)

async function fetchMaintenance() {
  loading.value = true
  try {
    const res = await apiClient.get('/maintenance')
    const d = res.data as any
    enabled.value = !!d.enabled
    msgText.value = d.message || ''
    resumedMsgText.value = d.resumed_message || ''
    title.value = d.title || ''
    allowAdminBypass.value = !!d.allow_admin_bypass
    updatedAt.value = d.updated_at || null
    if (d.defaults) {
      defaultMessage.value = d.defaults.message || ''
      defaultResumedMessage.value = d.defaults.resumed_message || ''
      defaultTitle.value = d.defaults.title || ''
    }
  } catch (err: any) {
    message.error('Failed to load maintenance settings: ' + (err.response?.data?.detail || err.message))
  } finally {
    loading.value = false
  }
}

async function save() {
  if (!canSave.value) return
  saving.value = true
  try {
    const res = await apiClient.put('/maintenance', {
      enabled: enabled.value,
      message: msgText.value,
      resumed_message: resumedMsgText.value,
      title: title.value,
      allow_admin_bypass: allowAdminBypass.value,
      notify_staff: notifyStaff.value,
    })
    const d = (res.data as any).maintenance || (res.data as any)
    if (d) {
      enabled.value = !!d.enabled
      updatedAt.value = d.updated_at || null
    }
    const broadcastNotice = notifyStaff.value ? ' (Staff broadcast sent)' : ''
    message.success(
      enabled.value
        ? `Maintenance mode ENABLED — bot will show custom notice.${broadcastNotice}`
        : `Maintenance mode disabled — bot is live again.${broadcastNotice}`
    )
  } catch (err: any) {
    message.error('Save failed: ' + (err.response?.data?.detail || err.message))
  } finally {
    saving.value = false
  }
}

function toggleEnabled(val: boolean) {
  if (val) {
    dialog.warning({
      title: 'Enable Maintenance Mode?',
      content: notifyStaff.value
        ? 'Telegram bot will enter maintenance and broadcast a notice to all staff users. Translation will be paused.'
        : 'Telegram bot will enter maintenance. Translation will be paused.',
      positiveText: 'Enable',
      negativeText: 'Cancel',
      onPositiveClick: () => {
        enabled.value = true
        save()
      },
      onNegativeClick: () => {
        enabled.value = false
      },
    })
  } else {
    dialog.info({
      title: 'Disable Maintenance Mode?',
      content: notifyStaff.value
        ? 'Bot will resume translation and broadcast a "Back Online" notice to staff users.'
        : 'Bot will resume translation for all users.',
      positiveText: 'Disable',
      negativeText: 'Cancel',
      onPositiveClick: () => {
        enabled.value = false
        save()
      },
      onNegativeClick: () => {
        enabled.value = true
      },
    })
  }
}

function restoreDefaults() {
  msgText.value = defaultMessage.value
  resumedMsgText.value = defaultResumedMessage.value
  title.value = defaultTitle.value
  message.info('Restored defaults — click Save to apply.')
}

function previewHtml(text: string): string {
  // naive HTML preview: escape then allow <b> <i> <code> <a>
  // For display we just show raw; NAlert will render as text — use v-html with sanitized subset
  return text
}

onMounted(() => {
  fetchMaintenance()
})
</script>

<template>
  <div class="space-y-6 max-w-4xl mx-auto pb-10">
    <!-- Header -->
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
      <div>
        <h1 class="text-xl font-bold text-gray-100 flex items-center gap-2">
          <ConstructOutline class="w-6 h-6 text-amber-400" />
          <span>Maintenance Mode</span>
          <NTag v-if="enabled" size="small" type="warning" :bordered="false" class="ml-2">ACTIVE</NTag>
          <NTag v-else size="small" type="success" :bordered="false" class="ml-2">LIVE</NTag>
        </h1>
        <p class="text-xs text-gray-400 mt-1">
          Put the Telegram bot into maintenance — users see your custom notice, no provider cost is incurred.
        </p>
      </div>
      <div class="flex items-center gap-2">
        <NButton secondary size="small" :loading="loading" @click="fetchMaintenance">
          <template #icon><RefreshOutline /></template>
          Refresh
        </NButton>
        <NButton secondary size="small" @click="restoreDefaults">
          <template #icon><ReloadOutline /></template>
          Defaults
        </NButton>
      </div>
    </div>

    <!-- Live banner preview when enabled -->
    <NAlert v-if="enabled" type="warning" :bordered="false" class="border border-amber-700/40 bg-amber-950/30">
      <div class="flex items-start gap-2">
        <WarningOutline class="w-5 h-5 text-amber-400 mt-0.5 shrink-0" />
        <div class="text-xs leading-relaxed text-amber-100/90">
          <div class="font-semibold text-amber-200">Maintenance is currently ACTIVE</div>
          <div class="mt-1">All Telegram messages (except admins when bypass is on) receive the notice below. No AI provider calls are made.</div>
          <div v-if="updatedAt" class="mt-1 text-[11px] text-amber-300/60">Updated: {{ updatedAt }} UTC</div>
        </div>
      </div>
    </NAlert>
    <NAlert v-else type="success" :bordered="false" class="border border-emerald-900/40 bg-emerald-950/20">
      <div class="flex items-center gap-2 text-xs text-emerald-200/90">
        <CheckmarkCircleOutline class="w-5 h-5 text-emerald-400 shrink-0" />
        <span>Bot is <b>live</b> — translations are being served normally.</span>
      </div>
    </NAlert>

    <NSpin :show="loading">
      <!-- Toggle Card -->
      <NCard size="small" class="border border-gray-800 bg-gray-900/40">
        <div class="flex items-center justify-between py-2">
          <div>
            <div class="text-sm font-semibold text-gray-100">Enable Maintenance Mode</div>
            <div class="text-[11px] text-gray-400 mt-0.5">
              When ON, the bot replies with your custom message to every user message and skips the AI provider entirely.
            </div>
          </div>
          <NSwitch
            :value="enabled"
            :loading="saving"
            size="large"
            @update:value="toggleEnabled"
          >
            <template #checked>ON</template>
            <template #unchecked>OFF</template>
          </NSwitch>
        </div>
        <div class="mt-3 flex items-center gap-2">
          <NCheckbox v-model:checked="allowAdminBypass">
            <span class="text-xs text-gray-300">Allow <b class="text-cyan-300">admins</b> to bypass maintenance (for testing)</span>
          </NCheckbox>
        </div>
        <div class="text-[11px] text-gray-500 mt-1 ml-6">
          Admins (role = admin in Staff Access) will still get translations. <code>/whoami</code> always works.
        </div>

        <div class="mt-3 flex items-center gap-2">
          <NCheckbox v-model:checked="notifyStaff">
            <span class="text-xs text-gray-300">Broadcast notification to <b class="text-emerald-400">Staff Users</b> on ON / OFF</span>
          </NCheckbox>
        </div>
        <div class="text-[11px] text-gray-500 mt-1 ml-6">
          When toggling ON, sends system update notice. When toggling OFF, announces that the bot is back online and ready for translation.
        </div>
      </NCard>

      <!-- Title -->
      <NCard size="small" class="border border-gray-800 bg-gray-900/40 mt-4">
        <template #header>
          <span class="text-sm font-semibold text-gray-200">Banner Title</span>
          <span class="text-[11px] text-gray-500 ml-2">Short label shown in the Admin banner & health check</span>
        </template>
        <NInput
          v-model:value="title"
          placeholder="e.g. Under Maintenance — back in 10 minutes"
          maxlength="120"
          show-count
          clearable
          :status="titleError ? 'error' : undefined"
        />
        <div v-if="titleError" class="text-[11px] text-red-400 mt-1">{{ titleError }}</div>
      </NCard>

      <!-- Message -->
      <NCard size="small" class="border border-gray-800 bg-gray-900/40 mt-4">
        <template #header>
          <div class="flex items-center justify-between w-full">
            <div>
              <span class="text-sm font-semibold text-gray-200">Maintenance Message</span>
              <span class="text-[11px] text-gray-500 ml-2">Sent to every Telegram user — HTML allowed (<code>&lt;b&gt; &lt;i&gt; &lt;code&gt; &lt;a&gt;</code>)</span>
            </div>
            <span class="text-[11px] font-mono text-gray-500">{{ msgText.length }} / 4000</span>
          </div>
        </template>

        <NInput
          v-model:value="msgText"
          type="textarea"
          :autosize="{ minRows: 5, maxRows: 12 }"
          placeholder="🔧 <b>Bot is under maintenance</b>&#10;&#10;Translation service is temporarily unavailable.&#10;Please try again in a few minutes."
          :status="messageError ? 'error' : undefined"
        />
        <div v-if="messageError" class="text-[11px] text-red-400 mt-1">{{ messageError }}</div>
        <div class="text-[11px] text-gray-500 mt-2 leading-relaxed">
          Tip: Telegram HTML is supported — <code>&lt;b&gt;bold&lt;/b&gt;</code>, <code>&lt;i&gt;italic&lt;/i&gt;</code>, <code>&lt;code&gt;</code>, and Telegram Premium animated emojis <code>&lt;tg-emoji emoji-id="..."&gt;🔧&lt;/tg-emoji&gt;</code> (or configure under <router-link to="/emojis" class="text-cyan-400 hover:underline">Animated Emojis</router-link>). Leave empty to use the built-in default.
        </div>

        <!-- Preview -->
        <div class="mt-4 rounded-lg border border-gray-800 bg-[#0b0f19] p-4">
          <div class="text-[11px] font-semibold tracking-wider text-gray-500 uppercase flex items-center gap-1.5 mb-2">
            <EyeOutline class="w-3.5 h-3.5" /> Preview (as Telegram renders HTML)
          </div>
          <div
            class="text-sm leading-relaxed whitespace-pre-wrap break-words text-gray-200"
            v-html="previewHtml(msgText || defaultMessage)"
          ></div>
          <div v-if="!msgText.trim()" class="text-[11px] text-gray-500 mt-2 italic">Showing default message (your field is empty).</div>
        </div>
      </NCard>

      <!-- Resumed Message (Back Online) -->
      <NCard size="small" class="border border-gray-800 bg-gray-900/40 mt-4">
        <template #header>
          <div class="flex items-center justify-between w-full">
            <div>
              <span class="text-sm font-semibold text-gray-200">Service Resumed Message (Bot is back online)</span>
              <span class="text-[11px] text-gray-500 ml-2">Broadcasted to staff when maintenance is turned OFF — HTML allowed</span>
            </div>
            <span class="text-[11px] font-mono text-gray-500">{{ resumedMsgText.length }} / 4000</span>
          </div>
        </template>

        <NInput
          v-model:value="resumedMsgText"
          type="textarea"
          :autosize="{ minRows: 4, maxRows: 10 }"
          placeholder="🟢 <b>Bot is back online</b>&#10;&#10;Maintenance is complete and translations are fully restored.&#10;You can continue sending messages to translate normally."
          :status="resumedMessageError ? 'error' : undefined"
        />
        <div v-if="resumedMessageError" class="text-[11px] text-red-400 mt-1">{{ resumedMessageError }}</div>
        <div class="text-[11px] text-gray-500 mt-2 leading-relaxed">
          Tip: Customize the message sent to Staff users when you turn maintenance OFF. Any standard <code>🟢</code> automatically upgrades to your custom animated emoji from <router-link to="/emojis" class="text-cyan-400 hover:underline">Animated Emojis</router-link>.
        </div>

        <!-- Preview -->
        <div class="mt-4 rounded-lg border border-gray-800 bg-[#0b0f19] p-4">
          <div class="text-[11px] font-semibold tracking-wider text-gray-500 uppercase flex items-center gap-1.5 mb-2">
            <EyeOutline class="w-3.5 h-3.5" /> Preview (as Telegram renders HTML)
          </div>
          <div
            class="text-sm leading-relaxed whitespace-pre-wrap break-words text-gray-200"
            v-html="previewHtml(resumedMsgText || defaultResumedMessage)"
          ></div>
          <div v-if="!resumedMsgText.trim()" class="text-[11px] text-gray-500 mt-2 italic">Showing default resumed message (your field is empty).</div>
        </div>
      </NCard>

      <!-- Save bar -->
      <div class="flex items-center justify-end gap-2 mt-4">
        <NButton secondary @click="fetchMaintenance">Discard</NButton>
        <NButton type="primary" :loading="saving" :disabled="!canSave" @click="save">
          <template #icon><SaveOutline /></template>
          Save Maintenance Settings
        </NButton>
      </div>
    </NSpin>
  </div>
</template>
