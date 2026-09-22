import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '../api'

export const useAuthStore = defineStore('auth', () => {
  const isAuthenticated = ref<boolean>(false)
  const appName = ref<string>('OpsTranslate Control Center')
  const mode = ref<string>('polling')
  const loading = ref<boolean>(false)
  const initialized = ref<boolean>(false)

  async function checkAuth(): Promise<boolean> {
    try {
      loading.value = true
      const res = await api.getMe()
      isAuthenticated.value = res.data.authenticated
      appName.value = res.data.app || 'OpsTranslate Control Center'
      mode.value = res.data.mode || 'polling'
      if (res.data.token) {
        localStorage.setItem('admin_token', res.data.token)
      }
      initialized.value = true
      return isAuthenticated.value
    } catch {
      isAuthenticated.value = false
      initialized.value = true
      return false
    } finally {
      loading.value = false
    }
  }

  async function login(password: string): Promise<boolean> {
    loading.value = true
    try {
      const res = await api.login(password)
      if (res.data.ok) {
        if (res.data.token) {
          localStorage.setItem('admin_token', res.data.token)
        }
        isAuthenticated.value = true
        await checkAuth()
        return true
      }
      return false
    } finally {
      loading.value = false
    }
  }

  async function logout(): Promise<void> {
    try {
      await api.logout()
    } finally {
      localStorage.removeItem('admin_token')
      isAuthenticated.value = false
      window.location.href = '/admin/login'
    }
  }

  return {
    isAuthenticated,
    appName,
    mode,
    loading,
    initialized,
    checkAuth,
    login,
    logout,
  }
})
