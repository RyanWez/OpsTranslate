<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useAuthStore } from '../../stores/auth'
import { useOverviewStore } from '../../stores/overview'
import { useProvidersStore } from '../../stores/providers'
import { useLogsStore } from '../../stores/logs'
import { useRealtimeStore } from '../../stores/realtime'
import { NButton, NTag } from 'naive-ui'
import { RefreshOutline, LogOutOutline } from '@vicons/ionicons5'

const authStore = useAuthStore()
const overviewStore = useOverviewStore()
const providersStore = useProvidersStore()
const logsStore = useLogsStore()
const realtimeStore = useRealtimeStore()

const serverClock = ref<string>('')
let timer: any = null

function updateClock() {
  const now = new Date()
  serverClock.value = now.toLocaleTimeString('en-GB', {
    timeZone: 'Asia/Yangon',
    hour12: false,
  }) + ' (Yangon)'
}

onMounted(() => {
  updateClock()
  timer = setInterval(updateClock, 1000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})

function handleRefresh() {
  overviewStore.fetchOverview()
  providersStore.fetchProviders()
  logsStore.fetchLogs()
}

function handleLogout() {
  authStore.logout()
}
</script>

<template>
  <header class="h-16 px-6 border-b border-gray-800 bg-[#0d1322]/80 backdrop-blur flex items-center justify-between z-20">
    <!-- Left: Brand & Live Heartbeat -->
    <div class="flex items-center space-x-4">
      <div class="flex items-center space-x-2.5">
        <div class="w-8 h-8 rounded-lg bg-gradient-to-tr from-emerald-500 to-cyan-500 flex items-center justify-center text-white font-bold text-lg shadow-lg shadow-emerald-500/20">
          🌐
        </div>
        <div class="flex flex-col">
          <div class="flex items-center space-x-2">
            <span class="font-bold text-gray-100 text-base tracking-tight">OpsTranslate</span>
            <NTag size="small" :bordered="false" type="info" class="text-[10px] font-mono uppercase px-1.5 py-0.5">
              {{ authStore.mode }}
            </NTag>
          </div>
          <span class="text-[11px] text-gray-400">Control Center & Gateway</span>
        </div>
      </div>

      <div class="h-4 w-[1px] bg-gray-700 hidden md:block"></div>

      <!-- Live SSE status indicator -->
      <div
        v-if="realtimeStore.isConnected"
        class="hidden sm:flex items-center space-x-2 px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20"
        title="Server-Sent Events (SSE) active - 0ms instant cross-device synchronization"
      >
        <span class="relative flex h-2 w-2">
          <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
          <span class="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
        </span>
        <span class="text-xs font-medium text-emerald-400">Instant Live (SSE)</span>
      </div>
      <div
        v-else-if="realtimeStore.isConnecting"
        class="hidden sm:flex items-center space-x-2 px-3 py-1 rounded-full bg-amber-500/10 border border-amber-500/20"
        title="Connecting to real-time stream..."
      >
        <span class="relative inline-flex rounded-full h-2 w-2 bg-amber-400 animate-pulse"></span>
        <span class="text-xs font-medium text-amber-400">Connecting SSE...</span>
      </div>
      <div
        v-else
        class="hidden sm:flex items-center space-x-2 px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 cursor-pointer"
        @click="realtimeStore.connect()"
        title="Live Sync active"
      >
        <span class="relative flex h-2 w-2">
          <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
          <span class="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
        </span>
        <span class="text-xs font-medium text-emerald-400">Live Sync</span>
      </div>
    </div>

    <!-- Right: Server Time, Refresh & Logout -->
    <div class="flex items-center space-x-3">
      <div class="hidden lg:flex items-center px-3 py-1 rounded bg-gray-900/60 border border-gray-800 text-xs font-mono text-gray-400">
        🕒 {{ serverClock }}
      </div>

      <NButton secondary circle size="small" @click="handleRefresh" title="Refresh Data">
        <template #icon>
          <RefreshOutline />
        </template>
      </NButton>

      <NButton quaternary size="small" @click="handleLogout" class="text-gray-400 hover:text-red-400">
        <template #icon>
          <LogOutOutline />
        </template>
        Logout
      </NButton>
    </div>
  </header>
</template>
