import { apiClient } from './client'
import type {
  MeResponse,
  OverviewStats,
  ProviderItem,
  ProviderPayload,
  TestProviderResult,
  StaffUser,
  UserPayload,
  PlaygroundResult,
  UsageLogItem,
  PolicyData,
  TranslationHistoryItem,
  TranslationHistoryResponse,
} from '../types'

export const api = {
  // Auth
  login: (password: string) => apiClient.post<{ ok: boolean; token: string }>('/login', { password }),
  logout: () => apiClient.post<{ ok: boolean }>('/logout'),
  getMe: () => apiClient.get<MeResponse>('/me'),

  // Overview
  getOverview: () => apiClient.get<OverviewStats>('/overview'),

  // Policy
  getPolicy: () => apiClient.get<PolicyData>('/policy'),
  testPolicyRegression: () =>
    apiClient.post<{
      ok: boolean
      total: number
      passed: number
      failed: number
      results: Record<string, string[]>
    }>('/policy/test-regression'),
  addDenyTerm: (payload: { lang: string; term: string }) =>
    apiClient.post<{ ok: boolean; term: string; lang: string; message: string }>('/policy/deny-terms', payload),
  deleteDenyTerm: (lang: string, term: string) =>
    apiClient.delete<{ ok: boolean; term: string; lang: string }>('/policy/deny-terms', { params: { lang, term } }),

  // Providers
  getProviders: () => apiClient.get<{ providers: ProviderItem[] }>('/providers'),
  createProvider: (payload: ProviderPayload) => apiClient.post<{ ok: boolean; id: number | null }>('/providers', payload),
  updateProvider: (id: number | string, payload: ProviderPayload) => apiClient.put<{ ok: boolean }>(`/providers/${id}`, payload),
  deleteProvider: (id: number | string) => apiClient.delete<{ ok: boolean }>(`/providers/${id}`),
  testProvider: (payload: { id?: number | string; base_url: string; api_key?: string; model: string; timeout_s?: number }) =>
    apiClient.post<TestProviderResult>('/providers/test', payload),


  // Users
  getUsers: () => apiClient.get<{ users: StaffUser[] }>('/users'),
  saveUser: (payload: UserPayload) => apiClient.post<{ ok: boolean }>('/users', payload),
  toggleUserStatus: (userId: number, active: boolean) =>
    apiClient.patch<{ ok: boolean; user_id: number; active: boolean }>(`/users/${userId}/status`, { active }),
  deleteUser: (userId: number) => apiClient.delete<{ ok: boolean }>(`/users/${userId}`),

  // Playground
  testPlayground: (text: string, dst?: string) =>
    apiClient.post<PlaygroundResult>('/playground', { text, dst }),

  // Logs
  getLogs: (params?: number | { limit?: number; start_time?: number | string; end_time?: number | string; provider?: string }) => {
    if (typeof params === 'number') {
      return apiClient.get<{ logs: UsageLogItem[] }>(`/logs?limit=${params}`)
    }
    return apiClient.get<{ logs: UsageLogItem[] }>('/logs', { params })
  },

  // Translation History & Staff Audits
  getHistory: (params?: {
    page?: number
    page_size?: number
    user_id?: number
    search?: string
    start_time?: number
    end_time?: number
    provider?: string
    status?: string
    src_lang?: string
    dst_lang?: string
  }) => apiClient.get<TranslationHistoryResponse>('/history', { params }),
  getHistoryDetail: (id: number) => apiClient.get<TranslationHistoryItem>(`/history/${id}`),
  pruneHistory: (days = 30) => apiClient.delete<{ ok: boolean; deleted_count: number }>('/history/prune', { params: { days } }),
}
