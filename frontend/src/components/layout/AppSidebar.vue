<script setup lang="ts">
import { computed, h, Component } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NMenu, NIcon } from 'naive-ui'
import {
  StatsChartOutline,
  FlashOutline,
  PeopleOutline,
  FlaskOutline,
  ChatboxEllipsesOutline,
  DocumentTextOutline,
  ShieldCheckmarkOutline,
  TerminalOutline,
} from '@vicons/ionicons5'

const route = useRoute()
const router = useRouter()

function renderIcon(icon: Component) {
  return () => h(NIcon, null, { default: () => h(icon) })
}

const activeKey = computed(() => (route.name as string) || 'overview')

const menuOptions = [
  {
    label: 'Overview',
    key: 'overview',
    icon: renderIcon(StatsChartOutline),
  },
  {
    label: 'Term Policy',
    key: 'policy',
    icon: renderIcon(ShieldCheckmarkOutline),
  },
  {
    label: 'AI Providers',
    key: 'providers',
    icon: renderIcon(FlashOutline),
  },
  {
    label: 'Staff Access',
    key: 'users',
    icon: renderIcon(PeopleOutline),
  },
  {
    label: 'Pipeline Playground',
    key: 'playground',
    icon: renderIcon(FlaskOutline),
  },
  {
    label: 'Translation History',
    key: 'history',
    icon: renderIcon(ChatboxEllipsesOutline),
  },
  {
    label: 'Bot Commands',
    key: 'commands',
    icon: renderIcon(TerminalOutline),
  },
  {
    label: 'Audit Logs',
    key: 'logs',
    icon: renderIcon(DocumentTextOutline),
  },
]

withDefaults(defineProps<{ isMobile?: boolean }>(), { isMobile: false })
const emit = defineEmits<{ (e: 'navigate', key: string): void }>()

function handleUpdateValue(key: string) {
  router.push({ name: key })
  emit('navigate', key)
}
</script>

<template>
  <aside
    :class="[
      'flex flex-col justify-between p-3 select-none h-full',
      isMobile ? 'w-full bg-[#0d1322]' : 'w-64 border-r border-gray-800 bg-[#0d1322]/90'
    ]"
  >
    <div class="space-y-1">
      <div class="px-3 py-2 text-[11px] font-semibold tracking-wider text-gray-500 uppercase">
        Navigation
      </div>
      <NMenu
        :value="activeKey"
        :options="menuOptions"
        @update:value="handleUpdateValue"
      />
    </div>

    <!-- Sidebar footer indicator -->
    <div class="p-3 rounded-lg bg-gray-900/80 border border-gray-800/80 space-y-1">
      <div class="flex items-center space-x-1.5 text-xs font-semibold text-gray-300">
        <span class="w-2 h-2 rounded-full bg-cyan-400"></span>
        <span>Term Policy Engine</span>
      </div>
      <div class="text-[11px] text-gray-500 font-mono">
        v1 (Strict Zero-Gaming)
      </div>
      <div class="text-[10px] text-gray-400">
        Entity protection + separator evasion filter active.
      </div>
    </div>
  </aside>
</template>
