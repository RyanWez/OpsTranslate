<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { NCard, NInput, NButton, useMessage } from 'naive-ui'
import { LockClosedOutline } from '@vicons/ionicons5'

const router = useRouter()
const authStore = useAuthStore()
const message = useMessage()

const password = ref('')
const loading = ref(false)

async function handleLogin() {
  if (!password.value) {
    message.warning('Please enter the admin password')
    return
  }

  loading.value = true
  try {
    const success = await authStore.login(password.value)
    if (success) {
      message.success('Authentication successful')
      router.push('/admin')
    } else {
      message.error('Incorrect admin password')
    }
  } catch (err: any) {
    message.error(err.response?.data?.detail || 'Authentication failed')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="min-h-screen w-screen bg-[#0b0f19] flex items-center justify-center p-4 relative overflow-hidden">
    <!-- Ambient background glow -->
    <div class="absolute -top-40 -left-40 w-96 h-96 bg-emerald-500/10 rounded-full blur-3xl pointer-events-none"></div>
    <div class="absolute -bottom-40 -right-40 w-96 h-96 bg-cyan-500/10 rounded-full blur-3xl pointer-events-none"></div>

    <NCard
      class="max-w-md w-full glass-panel border border-gray-800 shadow-2xl rounded-2xl p-2"
      :bordered="false"
    >
      <div class="text-center space-y-3 mb-6">
        <div class="w-14 h-14 mx-auto rounded-2xl bg-gradient-to-tr from-emerald-500 to-cyan-500 flex items-center justify-center text-white text-2xl shadow-lg shadow-emerald-500/30">
          🌐
        </div>
        <div>
          <h1 class="text-xl font-bold tracking-tight text-gray-100">OpsTranslate</h1>
          <p class="text-xs text-gray-400 mt-1">Control Center & Gateway Authentication</p>
        </div>
      </div>

      <form @submit.prevent="handleLogin" class="space-y-4">
        <div class="space-y-1.5">
          <label class="text-xs font-medium text-gray-300">Admin Secret Password</label>
          <NInput
            v-model:value="password"
            type="password"
            show-password-on="click"
            placeholder="Enter admin password"
            size="large"
            :disabled="loading"
            class="rounded-lg"
          >
            <template #prefix>
              <LockClosedOutline class="w-4 h-4 text-gray-500 mr-1" />
            </template>
          </NInput>
        </div>

        <NButton
          type="primary"
          block
          size="large"
          attr-type="submit"
          :loading="loading"
          class="font-medium mt-2"
        >
          Authenticate & Access
        </NButton>
      </form>

      <div class="mt-6 pt-4 border-t border-gray-800/60 text-center text-[11px] text-gray-500">
        Protected operational gateway • Zero-Gaming Engine Active
      </div>
    </NCard>
  </div>
</template>
