import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '../api'
import type { StaffUser, UserPayload } from '../types'

export const useUsersStore = defineStore('users', () => {
  const users = ref<StaffUser[]>([])
  const loading = ref<boolean>(false)

  async function fetchUsers(): Promise<void> {
    loading.value = true
    try {
      const res = await api.getUsers()
      users.value = res.data.users || []
    } finally {
      loading.value = false
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

  return {
    users,
    loading,
    fetchUsers,
    saveUser,
    deleteUser,
  }
})
