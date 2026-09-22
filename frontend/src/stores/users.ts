import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '../api'
import { useRealtimeStore } from './realtime'
import type { StaffUser, UserPayload } from '../types'

export const useUsersStore = defineStore('users', () => {
  const users = ref<StaffUser[]>([])
  const loading = ref<boolean>(false)
  let liveSyncTimer: any = null

  async function fetchUsers(silent = false): Promise<void> {
    if (!silent) {
      loading.value = true
    }
    try {
      const res = await api.getUsers()
      users.value = res.data.users || []
    } finally {
      if (!silent) {
        loading.value = false
      }
    }
  }

  function startLiveSync(intervalMs = 4000): void {
    stopLiveSync()
    fetchUsers()
    liveSyncTimer = setInterval(() => {
      if (document.visibilityState !== 'hidden') {
        const realtimeStore = useRealtimeStore()
        if (!realtimeStore.isConnected) {
          fetchUsers(true)
        }
      }
    }, intervalMs)
  }

  function stopLiveSync(): void {
    if (liveSyncTimer) {
      clearInterval(liveSyncTimer)
      liveSyncTimer = null
    }
  }

  async function saveUser(payload: UserPayload): Promise<boolean> {
    loading.value = true
    try {
      await api.saveUser(payload)
      await fetchUsers()
      return true
    } finally {
      loading.value = false
    }
  }

  async function deleteUser(userId: number): Promise<boolean> {
    loading.value = true
    try {
      await api.deleteUser(userId)
      await fetchUsers()
      return true
    } finally {
      loading.value = false
    }
  }

  async function toggleUserStatus(userId: number, active: boolean): Promise<boolean> {
    try {
      const target = users.value.find((u) => u.user_id === userId)
      if (target) {
        target.active = active
      }
      await api.toggleUserStatus(userId, active)
      return true
    } catch {
      await fetchUsers(true)
      return false
    }
  }

  return {
    users,
    loading,
    fetchUsers,
    startLiveSync,
    stopLiveSync,
    saveUser,
    toggleUserStatus,
    deleteUser,
  }
})
