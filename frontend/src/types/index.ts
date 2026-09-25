export interface MeResponse {
  authenticated: boolean
  token?: string | null
  app: string
  mode: string
}

export interface TelemetryPoint {
  label: string
  throughput: number
  latency_ms: number
}

export interface TelemetryData {
  current_throughput_5m: number
  current_p95_ms: number
  total_ok: number
  total_failed: number
  points: TelemetryPoint[]
}

export interface MaintenanceState {
  enabled: boolean
  message: string
  title: string
  allow_admin_bypass: boolean
  updated_at?: string | null
  updated_by?: number | null
}

export interface OverviewStats {
  status: string
  mode: string
  auto_toggle: boolean
  max_input_chars: number
  policy_version: string
  database_configured: boolean
  database_online: boolean
  redis_configured: boolean
  redis_online: boolean
  circuit_states: Record<string, 'closed' | 'half-open' | 'open' | string>
  active_provider_count: number
  today_spend_usd: number
  server_time: string
  telemetry?: TelemetryData
  maintenance?: MaintenanceState | null
}

export interface ProviderItem {
  id: number | null
  name: string
  base_url: string
  api_key_masked: string
  model: string
  priority: number
  enabled: boolean
  timeout_s: number
  breaker_state: string
  source: 'database' | 'memory/env'
}

export interface ProviderPayload {
  name: string
  base_url: string
  api_key?: string
  model: string
  priority: number
  enabled: boolean
  timeout_s: number
}

export interface TestProviderResult {
  ok: boolean
  status_code: number
  latency_ms: number
  model?: string
  sample_output?: string
  error?: string
}

export interface StaffUser {
  user_id: number
  display_name: string | null
  username?: string | null
  role: 'admin' | 'staff' | string
  daily_soft_cap: number
  active: boolean
  last_active_at?: string | null
  created_at?: string | null
}

export interface UserPayload {
  user_id: number
  display_name?: string | null
  username?: string | null
  role: string
  daily_soft_cap: number
  active: boolean
}

export interface PlaygroundResult {
  ok: boolean
  src_lang: string
  dst_lang: string
  provider_used?: string
  latency_ms?: number
  masked_input: string
  policy_hits: string[]
  raw_output?: string
  denial_hits?: string[]
  final_output?: string
  error?: string
}

export interface UsageLogItem {
  id: number
  user_id: number
  display_name?: string | null
  username?: string | null
  char_len: number
  provider: string
  latency_ms: number
  status: number | string
  policy_hits: string[]
  timestamp?: number
  created_at: string | null
}

export interface PolicyConcept {
  key: string
  approved: boolean
  enabled: boolean
  variants_my: string[]
  variants_en: string[]
  variants_zh: string[]
  outputs: Record<string, string>
}

export interface PolicyData {
  version: string | number
  concepts: PolicyConcept[]
  deny_terms: Record<string, string[]>
}

export interface TranslationHistoryItem {
  id: number
  timestamp?: number | null
  created_at: string
  user_id: number
  username?: string | null
  display_name?: string | null
  src_lang: string
  dst_lang: string
  input_text: string
  masked_text?: string | null
  output_text: string
  provider?: string | null
  latency_ms?: number | null
  char_len?: number | null
  policy_hits: string[]
  status?: string | null
  error_code?: string | null
}

export interface TranslationHistoryResponse {
  items: TranslationHistoryItem[]
  total: number
  page: number
  page_size: number
  total_pages: number
}
