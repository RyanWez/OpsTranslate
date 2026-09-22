<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { NDrawer, NDrawerContent } from 'naive-ui'
import AppHeader from './AppHeader.vue'
import AppSidebar from './AppSidebar.vue'
import { useRealtimeStore } from '../../stores/realtime'

const realtimeStore = useRealtimeStore()
const showMobileMenu = ref(false)

onMounted(() => {
  realtimeStore.connect()
})

onUnmounted(() => {
  realtimeStore.disconnect()
})
</script>

<template>
  <div class="h-screen w-screen flex flex-col overflow-hidden bg-[#0b0f19]">
    <AppHeader @toggle-menu="showMobileMenu = true" />
    <div class="flex-1 flex overflow-hidden">
      <!-- Desktop static sidebar -->
      <AppSidebar class="hidden md:flex shrink-0" />

      <!-- Mobile navigation drawer -->
      <NDrawer v-model:show="showMobileMenu" placement="left" :width="280">
        <NDrawerContent body-content-class="p-0 bg-[#0d1322]">
          <AppSidebar :is-mobile="true" @navigate="showMobileMenu = false" />
        </NDrawerContent>
      </NDrawer>

      <main class="flex-1 overflow-y-auto p-3 sm:p-6 bg-gradient-to-b from-[#0b0f19] to-[#0f172a]">
        <router-view />
      </main>
    </div>
  </div>
</template>
