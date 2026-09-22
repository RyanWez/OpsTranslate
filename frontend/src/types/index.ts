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
