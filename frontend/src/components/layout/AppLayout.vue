<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import AppHeader from './AppHeader.vue'
import AppSidebar from './AppSidebar.vue'
import { useRealtimeStore } from '../../stores/realtime'

const realtimeStore = useRealtimeStore()

onMounted(() => {
  realtimeStore.connect()
})

onUnmounted(() => {
  realtimeStore.disconnect()
})
</script>

<template>
  <div class="h-screen w-screen flex flex-col overflow-hidden bg-[#0b0f19]">
    <AppHeader />
    <div class="flex-1 flex overflow-hidden">
      <AppSidebar />
      <main class="flex-1 overflow-y-auto p-6 bg-gradient-to-b from-[#0b0f19] to-[#0f172a]">
        <router-view />
      </main>
    </div>
  </div>
</template>
