<script setup lang="ts">
import { onMounted, onUnmounted, computed } from 'vue'
import { useOverviewStore } from '../stores/overview'
import { NCard, NTag, NSpin, NButton } from 'naive-ui'
import {
  CashOutline,
  ShieldCheckmarkOutline,
  ServerOutline,
  LayersOutline,
  RefreshOutline,
  CheckmarkCircleOutline,
  WarningOutline,
  CloseCircleOutline,
} from '@vicons/ionicons5'

const overviewStore = useOverviewStore()

onMounted(() => {
  overviewStore.startAutoRefresh(15000)
})

onUnmounted(() => {
  overviewStore.stopAutoRefresh()
})

const stats = computed(() => overviewStore.stats)

const circuitCount = computed(() => {
  if (!stats.value?.circuit_states) return { total: 0, healthy: 0, tripped: 0 }
  const entries = Object.entries(stats.value.circuit_states)
  const total = entries.length
  const healthy = entries.filter(([, state]) => state === 'closed').length
  const tripped = total - healthy
  return { total, healthy, tripped }
})
</script>

<template>
  <div class="space-y-6 max-w-7xl mx-auto">
    <!-- Page Header -->
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
      <div>
        <h1 class="text-2xl font-bold text-gray-100 tracking-tight">System Overview</h1>
        <p class="text-xs text-gray-400 mt-0.5">Real-time health telemetry, circuit breaker states, and gateway statistics.</p>
      </div>
      <div class="flex items-center space-x-3">
        <NButton secondary size="small" @click="overviewStore.fetchOverview" :loading="overviewStore.loading">
          <template #icon>
            <RefreshOutline />
          </template>
          Refresh Stats
        </NButton>
      </div>
    </div>

    <NSpin :show="overviewStore.loading && !stats">
      <!-- 4 Core Metric Cards -->
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <!-- 1. Today Spend -->
        <NCard class="glass-panel border-gray-800 rounded-xl" :bordered="false">
          <div class="flex items-center justify-between">
            <span class="text-xs font-medium text-gray-400">Today's Estimated Spend</span>
            <div class="p-2 rounded-lg bg-emerald-500/10 text-emerald-400">
              <CashOutline class="w-5 h-5" />
            </div>
          </div>
          <div class="mt-3">
            <span class="text-2xl font-bold text-gray-100 font-mono">
              ${{ stats?.today_spend_usd.toFixed(4) || '0.0000' }}
            </span>
            <span class="text-xs text-gray-400 ml-1">USD</span>
          </div>
          <div class="mt-2 text-[11px] text-gray-500 flex items-center space-x-1">
            <span>Aggregated via Redis metering</span>
          </div>
        </NCard>

        <!-- 2. Circuit Breakers Health -->
        <NCard class="glass-panel border-gray-800 rounded-xl" :bordered="false">
          <div class="flex items-center justify-between">
            <span class="text-xs font-medium text-gray-400">Circuit Breakers</span>
            <div class="p-2 rounded-lg bg-cyan-500/10 text-cyan-400">
              <ShieldCheckmarkOutline class="w-5 h-5" />
            </div>
          </div>
          <div class="mt-3 flex items-baseline space-x-2">
            <span class="text-2xl font-bold text-gray-100 font-mono">
              {{ circuitCount.healthy }} / {{ circuitCount.total }}
            </span>
            <NTag
              size="small"
              :type="circuitCount.tripped === 0 ? 'success' : 'error'"
              class="text-[10px]"
            >
              {{ circuitCount.tripped === 0 ? 'All Stable' : `${circuitCount.tripped} Tripped` }}
            </NTag>
          </div>
          <div class="mt-2 text-[11px] text-gray-500">
            Active fallback LLM routes: {{ stats?.active_provider_count || 0 }}
          </div>
        </NCard>

        <!-- 3. Neon Postgres Database -->
        <NCard class="glass-panel border-gray-800 rounded-xl" :bordered="false">
          <div class="flex items-center justify-between">
            <span class="text-xs font-medium text-gray-400">Database (Neon Postgres)</span>
            <div class="p-2 rounded-lg bg-indigo-500/10 text-indigo-400">
              <ServerOutline class="w-5 h-5" />
            </div>
          </div>
          <div class="mt-3 flex items-center space-x-2">
            <span class="relative flex h-3 w-3">
              <span
                class="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75"
                :class="stats?.database_online ? 'bg-emerald-400' : 'bg-red-400'"
              ></span>
              <span
                class="relative inline-flex rounded-full h-3 w-3"
                :class="stats?.database_online ? 'bg-emerald-500' : 'bg-red-500'"
              ></span>
            </span>
            <span class="text-lg font-bold text-gray-100 font-mono">
              {{ stats?.database_online ? 'CONNECTED' : (stats?.database_configured ? 'DEGRADED' : 'NOT CONFIGURED') }}
            </span>
          </div>
          <div class="mt-2 text-[11px] text-gray-500">
            {{ stats?.database_configured ? 'Persistent storage active' : 'Running in transient memory mode' }}
          </div>
        </NCard>

        <!-- 4. Redis Cache & Rate Limiting -->
        <NCard class="glass-panel border-gray-800 rounded-xl" :bordered="false">
          <div class="flex items-center justify-between">
            <span class="text-xs font-medium text-gray-400">Redis Cache & Rate Limit</span>
            <div class="p-2 rounded-lg bg-purple-500/10 text-purple-400">
              <LayersOutline class="w-5 h-5" />
            </div>
          </div>
          <div class="mt-3 flex items-center space-x-2">
            <span class="relative flex h-3 w-3">
              <span
                class="relative inline-flex rounded-full h-3 w-3"
                :class="stats?.redis_online ? 'bg-emerald-500' : 'bg-amber-500'"
              ></span>
            </span>
            <span class="text-lg font-bold text-gray-100 font-mono">
              {{ stats?.redis_online ? 'ONLINE' : (stats?.redis_configured ? 'DISCONNECTED' : 'IN-MEMORY') }}
            </span>
          </div>
          <div class="mt-2 text-[11px] text-gray-500">
            {{ stats?.redis_online ? 'Distributed idempotency enabled' : 'In-memory failsoft fallback' }}
          </div>
        </NCard>
      </div>

      <!-- Telemetry Chart Card -->
      <NCard class="glass-panel border-gray-800 rounded-xl mt-6" :bordered="false">
        <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-4">
          <div class="flex items-center space-x-2">
            <span class="text-sm font-semibold text-gray-200">Gateway Telemetry & Traffic Trend</span>
            <span class="relative flex h-2 w-2">
              <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span class="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
            </span>
            <span class="text-[11px] text-emerald-400 font-mono">Live</span>
          </div>
          <div class="flex items-center space-x-4 text-xs">
            <div class="flex items-center space-x-1.5">
              <span class="w-2.5 h-2.5 rounded-full bg-cyan-400"></span>
              <span class="text-gray-400">Request Throughput</span>
            </div>
            <div class="flex items-center space-x-1.5">
              <span class="w-2.5 h-2.5 rounded-full bg-emerald-400"></span>
              <span class="text-gray-400">P95 Latency</span>
            </div>
          </div>
        </div>

        <div class="w-full h-44 relative">
          <svg viewBox="0 0 800 160" class="w-full h-full overflow-visible">
            <defs>
              <linearGradient id="grad-cyan" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="#06b6d4" stop-opacity="0.35" />
                <stop offset="100%" stop-color="#06b6d4" stop-opacity="0.0" />
              </linearGradient>
              <linearGradient id="grad-emerald" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="#10b981" stop-opacity="0.25" />
                <stop offset="100%" stop-color="#10b981" stop-opacity="0.0" />
              </linearGradient>
            </defs>

            <!-- Grid Lines -->
            <line x1="0" y1="30" x2="800" y2="30" stroke="rgba(255,255,255,0.04)" stroke-dasharray="4" />
            <line x1="0" y1="75" x2="800" y2="75" stroke="rgba(255,255,255,0.04)" stroke-dasharray="4" />
            <line x1="0" y1="120" x2="800" y2="120" stroke="rgba(255,255,255,0.04)" stroke-dasharray="4" />

            <!-- Cyan Throughput Area & Line -->
            <path
              d="M0,130 C120,120 180,60 260,85 C340,110 400,30 480,45 C560,60 640,115 720,70 C760,50 780,40 800,45 L800,150 L0,150 Z"
              fill="url(#grad-cyan)"
            />
            <path
              d="M0,130 C120,120 180,60 260,85 C340,110 400,30 480,45 C560,60 640,115 720,70 C760,50 780,40 800,45"
              fill="none"
              stroke="#06b6d4"
              stroke-width="2.5"
            />

            <!-- Emerald Latency Area & Line -->
            <path
              d="M0,140 C140,135 220,105 300,115 C400,125 480,95 580,100 C680,105 740,80 800,85 L800,150 L0,150 Z"
              fill="url(#grad-emerald)"
            />
            <path
              d="M0,140 C140,135 220,105 300,115 C400,125 480,95 580,100 C680,105 740,80 800,85"
              fill="none"
              stroke="#10b981"
              stroke-width="2"
            />

            <!-- Highlight Pulse Point -->
            <circle cx="480" cy="45" r="5" fill="#06b6d4" class="animate-pulse" />
            <circle cx="480" cy="45" r="9" fill="none" stroke="#06b6d4" stroke-opacity="0.5" />
          </svg>
        </div>

        <div class="flex justify-between text-[11px] font-mono text-gray-500 mt-2 border-t border-gray-800/60 pt-2">
          <span>00:00</span>
          <span>04:00</span>
          <span>08:00</span>
          <span>12:00</span>
          <span>16:00</span>
          <span>20:00</span>
          <span class="text-cyan-400 font-semibold">Live (Now)</span>
        </div>
      </NCard>

      <!-- Circuit Breakers Detailed Grid -->
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-6 mt-6">
        <NCard class="glass-panel border-gray-800 rounded-xl lg:col-span-2" :bordered="false" title="AI Provider Circuit Breakers">
          <div v-if="stats?.circuit_states && Object.keys(stats.circuit_states).length > 0" class="divide-y divide-gray-800/80">
            <div
              v-for="(state, name) in stats.circuit_states"
              :key="name"
              class="py-3 flex items-center justify-between"
            >
              <div class="flex items-center space-x-3">
                <div class="w-2.5 h-2.5 rounded-full" :class="{
                  'bg-emerald-500': state === 'closed',
                  'bg-amber-500': state === 'half-open',
                  'bg-red-500': state === 'open'
                }"></div>
                <div>
                  <div class="text-sm font-semibold text-gray-200 font-mono">{{ name }}</div>
                  <div class="text-[11px] text-gray-500">
                    {{ state === 'closed' ? 'Healthy • Accepting translations' : (state === 'half-open' ? 'Trial recovery probe in-flight' : 'Tripped • Failed 3+ consecutive times') }}
                  </div>
                </div>
              </div>

              <div>
                <NTag
                  size="small"
                  :type="state === 'closed' ? 'success' : (state === 'half-open' ? 'warning' : 'error')"
                  class="uppercase font-mono text-[11px]"
                >
                  <template #icon>
                    <CheckmarkCircleOutline v-if="state === 'closed'" />
                    <WarningOutline v-else-if="state === 'half-open'" />
                    <CloseCircleOutline v-else />
                  </template>
                  {{ state }}
                </NTag>
              </div>
            </div>
          </div>
          <div v-else class="text-center py-8 text-gray-500 text-sm">
            No circuit breakers registered yet.
          </div>
        </NCard>

        <!-- Gateway Settings & Engine Specs -->
        <NCard class="glass-panel border-gray-800 rounded-xl" :bordered="false" title="Gateway Policy Engine">
          <div class="space-y-4">
            <div class="flex items-center justify-between pb-3 border-b border-gray-800/60">
              <span class="text-xs text-gray-400">Policy Version</span>
              <span class="text-xs font-mono text-cyan-400 font-semibold">{{ stats?.policy_version || 'v1' }}</span>
            </div>

            <div class="flex items-center justify-between pb-3 border-b border-gray-800/60">
              <span class="text-xs text-gray-400">Auto Language Toggle</span>
              <NTag size="small" :type="stats?.auto_toggle ? 'success' : 'default'" class="text-[10px]">
                {{ stats?.auto_toggle ? 'ENABLED (MY ↔ EN)' : 'DISABLED' }}
              </NTag>
            </div>

            <div class="flex items-center justify-between pb-3 border-b border-gray-800/60">
              <span class="text-xs text-gray-400">Max Input Limit</span>
              <span class="text-xs font-mono text-gray-200">{{ stats?.max_input_chars || 500 }} characters</span>
            </div>

            <div class="flex items-center justify-between pb-3 border-b border-gray-800/60">
              <span class="text-xs text-gray-400">Runtime Mode</span>
              <span class="text-xs font-mono text-emerald-400 uppercase">{{ stats?.mode || 'polling' }}</span>
            </div>

            <div class="flex items-center justify-between">
              <span class="text-xs text-gray-400">Server Local Time</span>
              <span class="text-xs font-mono text-gray-300">{{ stats?.server_time || '--' }}</span>
            </div>
          </div>
        </NCard>
      </div>
    </NSpin>
  </div>
</template>
