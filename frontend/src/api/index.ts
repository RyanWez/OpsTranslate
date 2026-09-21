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
} from '../types'

export const api = {
  // Auth
  login: (password: string) => apiClient.post<{ ok: boolean; token: string }>('/login', { password }),
  logout: () => apiClient.post<{ ok: boolean }>('/logout'),
  getMe: () => apiClient.get<MeResponse>('/me'),

  // Overview
  getOverview: () => apiClient.get<OverviewStats>('/overview'),

  // Providers
  getProviders: () => apiClient.get<{ providers: ProviderItem[] }>('/providers'),
  createProvider: (payload: ProviderPayload) => apiClient.post<{ ok: boolean; id: number | null }>('/providers', payload),
  updateProvider: (id: number, payload: ProviderPayload) => apiClient.put<{ ok: boolean }>(`/providers/${id}`, payload),
  deleteProvider: (id: number) => apiClient.delete<{ ok: boolean }>(`/providers/${id}`),
  testProvider: (payload: { base_url: string; api_key: string; model: string; timeout_s?: number }) =>
    apiClient.post<TestProviderResult>('/providers/test', payload),

  // Users
  getUsers: () => apiClient.get<{ users: StaffUser[] }>('/users'),
  saveUser: (payload: UserPayload) => apiClient.post<{ ok: boolean }>('/users', payload),
  deleteUser: (userId: number) => apiClient.delete<{ ok: boolean }>(`/users/${userId}`),

  // Playground
  testPlayground: (text: string, dst?: string) =>
    apiClient.post<PlaygroundResult>('/playground', { text, dst }),

  // Logs
  getLogs: (limit: number = 50) => apiClient.get<{ logs: UsageLogItem[] }>(`/logs?limit=${limit}`),
}
