import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useProvidersStore } from './providers'
import { useLogsStore } from './logs'
import { useOverviewStore } from './overview'
import { useUsersStore } from './users'
import type { UsageLogItem, TelemetryData } from '../types'

export const useRealtimeStore = defineStore('realtime', () => {
  const isConnected = ref<boolean>(false)
  const isConnecting = ref<boolean>(false)
  const lastEventTime = ref<string>('')
  let eventSource: EventSource | null = null
  let reconnectTimer: any = null

  function connect() {
    if (eventSource) return

    isConnecting.value = true
    const token = localStorage.getItem('admin_token') || ''
    const url = token ? `/api/admin/events?token=${encodeURIComponent(token)}` : '/api/admin/events'

    try {
      eventSource = new EventSource(url, { withCredentials: true })

      eventSource.onopen = () => {
        isConnected.value = true
        isConnecting.value = false
        if (reconnectTimer) {
          clearTimeout(reconnectTimer)
          reconnectTimer = null
        }
      }

      eventSource.addEventListener('connected', () => {
        isConnected.value = true
        isConnecting.value = false
      })

      eventSource.addEventListener('providers_changed', () => {
        lastEventTime.value = new Date().toLocaleTimeString()
        const providersStore = useProvidersStore()
        providersStore.fetchProviders(true)
        const overviewStore = useOverviewStore()
        overviewStore.fetchOverview(true)
      })

      eventSource.addEventListener('usage_log', (e: MessageEvent) => {
        lastEventTime.value = new Date().toLocaleTimeString()
        try {
          const payload = JSON.parse(e.data)
          const item: UsageLogItem = payload.data || payload
          const logsStore = useLogsStore()
          logsStore.addLiveLog(item)
        } catch (err) {
          console.error('SSE usage_log parse error', err)
        }
      })

      eventSource.addEventListener('telemetry_update', (e: MessageEvent) => {
        lastEventTime.value = new Date().toLocaleTimeString()
        try {
          const payload = JSON.parse(e.data)
          const telemetry: TelemetryData = payload.data || payload
          const overviewStore = useOverviewStore()
          overviewStore.updateTelemetry(telemetry)
        } catch (err) {
          console.error('SSE telemetry_update parse error', err)
        }
      })

      eventSource.addEventListener('overview_changed', () => {
        lastEventTime.value = new Date().toLocaleTimeString()
        const overviewStore = useOverviewStore()
        overviewStore.fetchOverview(true)
      })

      eventSource.addEventListener('users_changed', () => {
        lastEventTime.value = new Date().toLocaleTimeString()
        const usersStore = useUsersStore()
        usersStore.fetchUsers(true)
      })

      eventSource.onerror = () => {
        isConnected.value = false
        isConnecting.value = false
        disconnect()
        // Auto-reconnect after 2.5 seconds
        if (!reconnectTimer) {
          reconnectTimer = setTimeout(() => {
            reconnectTimer = null
            connect()
          }, 2500)
        }
      }
    } catch (err) {
      isConnecting.value = false
      isConnected.value = false
    }
  }

  function disconnect() {
    if (eventSource) {
      eventSource.close()
      eventSource = null
    }
    isConnected.value = false
    isConnecting.value = false
  }

  return {
    isConnected,
    isConnecting,
    lastEventTime,
    connect,
    disconnect,
  }
})
