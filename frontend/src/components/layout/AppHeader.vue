<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useAuthStore } from '../../stores/auth'
import { computed } from 'vue'
import { useOverviewStore } from '../../stores/overview'
import { useProvidersStore } from '../../stores/providers'
import { useLogsStore } from '../../stores/logs'
import { useRealtimeStore } from '../../stores/realtime'
import { NButton, NTag } from 'naive-ui'
import { RefreshOutline, LogOutOutline, MenuOutline } from '@vicons/ionicons5'

const emit = defineEmits<{ (e: 'toggle-menu'): void }>()

const authStore = useAuthStore()
const overviewStore = useOverviewStore()
const providersStore = useProvidersStore()
const logsStore = useLogsStore()
const realtimeStore = useRealtimeStore()

const maintenanceActive = computed(() => !!overviewStore.stats?.maintenance?.enabled)
const maintenanceTitle = computed(() => overviewStore.stats?.maintenance?.title || 'Maintenance active')

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
  <header class="h-16 px-3 sm:px-6 border-b border-gray-800 bg-[#0d1322]/90 backdrop-blur flex items-center justify-between z-20">
    <!-- Left: Hamburger (Mobile) + Brand -->
    <div class="flex items-center space-x-2 sm:space-x-4">
      <NButton
        quaternary
        circle
        size="small"
        class="md:hidden text-gray-300 hover:text-white"
        @click="emit('toggle-menu')"
        title="Open Navigation Menu"
      >
        <template #icon>
          <MenuOutline />
        </template>
      </NButton>

      <div class="flex items-center space-x-2 sm:space-x-2.5">
        <div class="w-8 h-8 rounded-lg bg-gradient-to-tr from-emerald-500 to-cyan-500 flex items-center justify-center text-white font-bold text-base sm:text-lg shadow-lg shadow-emerald-500/20 shrink-0">
          🌐
        </div>
        <div class="flex flex-col">
          <div class="flex items-center space-x-1.5 sm:space-x-2">
            <span class="font-bold text-gray-100 text-sm sm:text-base tracking-tight">OpsTranslate</span>
            <NTag size="small" :bordered="false" type="info" class="text-[9px] sm:text-[10px] font-mono uppercase px-1 py-0.5">
              {{ authStore.mode }}
            </NTag>
          </div>
          <span class="text-[10px] sm:text-[11px] text-gray-400 truncate max-w-[120px] sm:max-w-none">Control Center</span>
        </div>
      </div>
    </div>

    <!-- Right: Server Time, Status, Refresh & Logout -->
    <div class="flex items-center space-x-2 sm:space-x-3">
      <!-- Global maintenance badge (header) -->
      <router-link
        v-if="maintenanceActive"
        to="/maintenance"
        class="hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-amber-500/15 border border-amber-500/30 hover:bg-amber-500/25 transition"
        :title="maintenanceTitle"
      >
        <span class="w-2 h-2 rounded-full bg-amber-400 animate-pulse"></span>
        <span class="text-xs font-semibold text-amber-300">Maintenance</span>
      </router-link>
      <router-link
        v-if="maintenanceActive"
        to="/maintenance"
        class="sm:hidden flex items-center justify-center w-7 h-7 rounded-full bg-amber-500/15 border border-amber-500/30"
        title="Maintenance active"
      >
        <span class="w-2 h-2 rounded-full bg-amber-400 animate-pulse"></span>
      </router-link>

      <!-- Live SSE status indicator -->
      <div
        v-if="realtimeStore.isConnected"
        class="flex items-center space-x-1.5 sm:space-x-2 px-2.5 sm:px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20"
        title="Server-Sent Events (SSE) active - 0ms instant cross-device synchronization"
      >
        <span class="relative flex h-2 w-2">
          <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
          <span class="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
        </span>
        <span class="text-xs font-medium text-emerald-400 hidden sm:inline">Instant Live</span>
        <span class="text-[10px] font-mono text-emerald-300 font-semibold">SSE</span>
      </div>
      <div
        v-else-if="realtimeStore.isConnecting"
        class="flex items-center space-x-1.5 sm:space-x-2 px-2 sm:px-3 py-1 rounded-full bg-amber-500/10 border border-amber-500/20"
        title="Connecting to real-time stream..."
      >
        <span class="relative inline-flex rounded-full h-2 w-2 bg-amber-400 animate-pulse"></span>
        <span class="text-xs font-medium text-amber-400">Connecting...</span>
      </div>
      <div
        v-else
        class="flex items-center space-x-1.5 sm:space-x-2 px-2.5 sm:px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 cursor-pointer"
        @click="realtimeStore.connect()"
        title="Live Sync active"
      >
        <span class="relative flex h-2 w-2">
          <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
          <span class="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
        </span>
        <span class="text-xs font-medium text-emerald-400">Live</span>
      </div>

      <div class="hidden lg:flex items-center px-3 py-1 rounded bg-gray-900/60 border border-gray-800 text-xs font-mono text-gray-400">
        🕒 {{ serverClock }}
      </div>

      <NButton secondary circle size="small" @click="handleRefresh" title="Refresh Data">
        <template #icon>
          <RefreshOutline />
        </template>
      </NButton>

      <NButton quaternary size="small" @click="handleLogout" class="text-gray-400 hover:text-red-400 px-1.5 sm:px-2.5">
        <template #icon>
          <LogOutOutline />
        </template>
        <span class="hidden sm:inline">Logout</span>
      </NButton>
    </div>
  </header>
</template>
