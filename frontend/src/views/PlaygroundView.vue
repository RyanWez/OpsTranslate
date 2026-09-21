<script setup lang="ts">
import { usePlaygroundStore } from '../stores/playground'
import {
  NCard,
  NButton,
  NInput,
  NSelect,
  NTag,
  NAlert,
} from 'naive-ui'
import {
  FlaskOutline,
  ShieldCheckmarkOutline,
  CheckmarkCircleOutline,
} from '@vicons/ionicons5'

const playgroundStore = usePlaygroundStore()

const sampleInputs = [
  {
    label: '🇲🇲 Myanmar Gaming Issue',
    text: 'မင်္ဂလာပါ ဂိမ်းအိုင်ဒီ မှားနေပါတယ် https://x.co/ops 0912345678 @support',
  },
  {
    label: '🇬🇧 English Support Reply',
    text: 'Please check your User ID and contact support at https://ops.internal/help',
  },
  {
    label: '⚠️ Separator Evasion Attempt',
    text: 'g-a-m-e platform deposit error 1000',
  },
]

function applySample(text: string) {
  playgroundStore.inputText = text
  playgroundStore.runPipeline()
}

const dstOptions = [
  { label: 'Auto Toggle (MY ↔ EN)', value: 'auto' },
  { label: 'Force Myanmar (my)', value: 'my' },
  { label: 'Force English (en)', value: 'en' },
]
</script>

<template>
  <div class="space-y-6 max-w-7xl mx-auto">
    <!-- Header -->
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
      <div>
        <h1 class="text-2xl font-bold text-gray-100 tracking-tight">Pipeline Playground & Sandbox</h1>
        <p class="text-xs text-gray-400 mt-0.5">Test real-time entity protection, zero-gaming term masking, LLM routing, and leak sanitization.</p>
      </div>
    </div>

    <!-- Input Form Card -->
    <NCard class="glass-panel border-gray-800 rounded-xl" :bordered="false">
      <div class="space-y-4">
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div class="flex items-center space-x-2">
            <span class="text-xs text-gray-400">Quick Samples:</span>
            <NButton
              v-for="s in sampleInputs"
              :key="s.label"
              size="tiny"
              secondary
              @click="applySample(s.text)"
            >
              {{ s.label }}
            </NButton>
          </div>

          <div class="w-56">
            <NSelect
              v-model:value="playgroundStore.dstLang"
              :options="dstOptions"
              size="small"
              placeholder="Target Direction"
            />
          </div>
        </div>

        <NInput
          v-model:value="playgroundStore.inputText"
          type="textarea"
          :rows="3"
          placeholder="Enter text to translate (e.g. မင်္ဂလာပါ ဂိမ်းအိုင်ဒီ မှားနေပါတယ် https://x.co/a 0912345678)"
          maxlength="500"
          show-count
        />

        <div class="flex justify-between items-center pt-1">
          <span class="text-[11px] text-gray-500">
            Max limit 500 chars • Evaluates against policy v1 dictionary
          </span>
          <NButton
            type="primary"
            :loading="playgroundStore.loading"
            @click="playgroundStore.runPipeline"
          >
            <template #icon>
              <FlaskOutline />
            </template>
            Execute Pipeline Test
          </NButton>
        </div>
      </div>
    </NCard>

    <!-- Error Alert -->
    <NAlert v-if="playgroundStore.error" type="error" title="Pipeline Error" class="rounded-xl">
      {{ playgroundStore.error }}
    </NAlert>

    <!-- Result Flow Visualization -->
    <div v-if="playgroundStore.result" class="space-y-4">
      <div class="flex items-center justify-between">
        <div class="flex items-center space-x-2">
          <span class="text-sm font-semibold text-gray-200">Execution Telemetry</span>
          <NTag size="small" type="success" class="font-mono text-xs">
            {{ playgroundStore.result.latency_ms }} ms
          </NTag>
          <NTag size="small" type="info" class="font-mono text-xs">
            Provider: {{ playgroundStore.result.provider_used || 'Active' }}
          </NTag>
          <NTag size="small" class="font-mono text-xs uppercase">
            {{ playgroundStore.result.src_lang }} ➔ {{ playgroundStore.result.dst_lang }}
          </NTag>
        </div>
      </div>

      <!-- Pipeline 5 Stages Breakdown -->
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <!-- Stage 1 & 2: Masked Input & Policy Hits -->
        <NCard class="glass-panel border-gray-800 rounded-xl" :bordered="false" title="Stage 1 & 2: Entity & Term Masking">
          <div class="space-y-3">
            <div>
              <span class="text-xs text-gray-400">Masked Prompt Sent to LLM:</span>
              <div class="p-3 rounded-lg bg-gray-900/90 border border-gray-800 font-mono text-xs text-cyan-300 break-words mt-1">
                {{ playgroundStore.result.masked_input }}
              </div>
            </div>

            <div>
              <span class="text-xs text-gray-400">Policy Concepts Detected:</span>
              <div class="flex flex-wrap gap-1.5 mt-1">
                <NTag
                  v-for="hit in playgroundStore.result.policy_hits"
                  :key="hit"
                  size="small"
                  type="warning"
                  class="font-mono text-[11px]"
                >
                  ⟦T:{{ hit }}⟧
                </NTag>
                <span v-if="playgroundStore.result.policy_hits.length === 0" class="text-xs text-gray-500 italic">
                  No policy terms triggered.
                </span>
              </div>
            </div>
          </div>
        </NCard>

        <!-- Stage 3 & 4: LLM Output & Denial Scan -->
        <NCard class="glass-panel border-gray-800 rounded-xl" :bordered="false" title="Stage 3 & 4: LLM Output & Sanitization">
          <div class="space-y-3">
            <div>
              <span class="text-xs text-gray-400">Raw Provider Response:</span>
              <div class="p-3 rounded-lg bg-gray-900/90 border border-gray-800 font-mono text-xs text-gray-300 break-words mt-1">
                {{ playgroundStore.result.raw_output || '—' }}
              </div>
            </div>

            <div>
              <span class="text-xs text-gray-400">Denial Violations:</span>
              <div class="flex flex-wrap gap-1.5 mt-1">
                <NTag
                  v-for="deny in playgroundStore.result.denial_hits"
                  :key="deny"
                  size="small"
                  type="error"
                  class="font-mono text-[11px]"
                >
                  {{ deny }}
                </NTag>
                <span v-if="!playgroundStore.result.denial_hits || playgroundStore.result.denial_hits.length === 0" class="text-xs text-emerald-400 flex items-center space-x-1">
                  <CheckmarkCircleOutline class="w-4 h-4" />
                  <span>Passed deny-scan (Zero leaks)</span>
                </span>
              </div>
            </div>
          </div>
        </NCard>
      </div>

      <!-- Stage 5: Final Delivery Output -->
      <NCard class="glass-panel border-emerald-500/30 rounded-xl glow-emerald" :bordered="false">
        <div class="space-y-2">
          <div class="flex items-center justify-between">
            <div class="flex items-center space-x-2 text-emerald-400">
              <ShieldCheckmarkOutline class="w-5 h-5" />
              <span class="font-bold text-sm">Stage 5: Final Verified Translation Output</span>
            </div>
            <NTag size="small" type="success" class="text-[10px] font-mono uppercase">
              Delivered to Telegram User
            </NTag>
          </div>
          <div class="p-4 rounded-xl bg-emerald-950/20 border border-emerald-500/20 text-emerald-100 font-sans text-base leading-relaxed break-words">
            {{ playgroundStore.result.final_output }}
          </div>
        </div>
      </NCard>
    </div>
  </div>
</template>
