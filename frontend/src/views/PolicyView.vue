<script setup lang="ts">
import { ref, onMounted, computed, h } from 'vue'
import { usePolicyStore } from '../stores/policy'
import { api } from '../api'
import {
  NCard,
  NButton,
  NInput,
  NDataTable,
  NTag,
  NTabs,
  NTabPane,
  NSpin,
  NModal,
  NSelect,
  NForm,
  NFormItem,
  useMessage,
  useDialog,
} from 'naive-ui'
import {
  ShieldCheckmarkOutline,
  RefreshOutline,
  SearchOutline,
  AlertCircleOutline,
  PlayCircleOutline,
  CheckmarkCircleOutline,
  CloseCircleOutline,
  AddOutline,
} from '@vicons/ionicons5'
import type { PolicyConcept } from '../types'

const policyStore = usePolicyStore()
const message = useMessage()
const dialog = useDialog()
const runningRegression = ref(false)
const showRegressionModal = ref(false)
const regressionResults = ref<{
  ok: boolean
  total: number
  passed: number
  failed: number
  results: Record<string, string[]>
} | null>(null)

const showAddDenyModal = ref(false)
const addingDenyTerm = ref(false)
const denyForm = ref({
  lang: 'en',
  term: '',
})

const langOptions = [
  { label: 'English (en)', value: 'en' },
  { label: 'Myanmar (my)', value: 'my' },
  { label: 'Chinese (zh)', value: 'zh' },
]

function openAddDenyModal(defaultLang = 'en') {
  denyForm.value = { lang: defaultLang, term: '' }
  showAddDenyModal.value = true
}

async function handleAddDenyTerm() {
  if (!denyForm.value.term.trim()) {
    message.warning('Please enter a term')
    return
  }
  addingDenyTerm.value = true
  try {
    const res = await api.addDenyTerm({
      lang: denyForm.value.lang,
      term: denyForm.value.term.trim(),
    })
    message.success(res.data.message || 'Forbidden term added')
    showAddDenyModal.value = false
    await policyStore.fetchPolicy()
  } catch (err: any) {
    message.error(err.response?.data?.detail || 'Failed to add forbidden term')
  } finally {
    addingDenyTerm.value = false
  }
}

function handleDeleteDenyTerm(lang: string, term: string) {
  dialog.warning({
    title: 'Confirm Removal',
    content: `Remove "${term}" from forbidden terms (${lang.toUpperCase()})?`,
    positiveText: 'Remove',
    negativeText: 'Cancel',
    onPositiveClick: async () => {
      try {
        await api.deleteDenyTerm(lang, term)
        message.success(`Term "${term}" removed`)
        await policyStore.fetchPolicy()
      } catch (err: any) {
        message.error(err.response?.data?.detail || 'Failed to remove term')
      }
    },
  })
}

async function handleRunRegression() {
  runningRegression.value = true
  try {
    const res = await api.testPolicyRegression()
    regressionResults.value = res.data
    showRegressionModal.value = true
    if (res.data.ok) {
      message.success(`Regression Suite Passed! (${res.data.passed}/${res.data.total} cases)`)
    } else {
      message.error(`Regression Suite: ${res.data.failed} cases failed`)
    }
  } catch (err: any) {
    message.error(err.response?.data?.detail || 'Failed to run regression tests')
  } finally {
    runningRegression.value = false
  }
}

onMounted(() => {
  policyStore.fetchPolicy()
})

const searchQuery = ref('')

const filteredConcepts = computed(() => {
  if (!policyStore.policy?.concepts) return []
  if (!searchQuery.value.trim()) return policyStore.policy.concepts

  const q = searchQuery.value.trim().toLowerCase()
  return policyStore.policy.concepts.filter((c) => {
    const matchKey = c.key.toLowerCase().includes(q)
    const matchMy = c.variants_my.some((v) => v.toLowerCase().includes(q))
    const matchEn = c.variants_en.some((v) => v.toLowerCase().includes(q))
    const matchOut = Object.values(c.outputs).some((v) => v.toLowerCase().includes(q))
    return matchKey || matchMy || matchEn || matchOut
  })
})

const stats = computed(() => {
  if (!policyStore.policy) return { concepts: 0, myVariants: 0, enVariants: 0, denyTerms: 0 }
  const concepts = policyStore.policy.concepts.length
  let myVariants = 0
  let enVariants = 0
  for (const c of policyStore.policy.concepts) {
    myVariants += c.variants_my.length
    enVariants += c.variants_en.length
  }
  let denyTerms = 0
  if (policyStore.policy.deny_terms) {
    for (const list of Object.values(policyStore.policy.deny_terms)) {
      denyTerms += list.length
    }
  }
  return { concepts, myVariants, enVariants, denyTerms }
})

const columns = [
  {
    title: 'Concept Key',
    key: 'key',
    width: 170,
    render(row: PolicyConcept) {
      return h(
        NTag,
        { type: 'info', size: 'small', class: 'font-mono text-xs' },
        { default: () => `⟦T:${row.key}⟧` }
      )
    },
  },
  {
    title: 'Approved Neutral Outputs',
    key: 'outputs',
    width: 220,
    render(row: PolicyConcept) {
      return h('div', { class: 'space-y-1 text-xs font-mono' }, [
        row.outputs.en ? h('div', { class: 'text-emerald-300' }, `EN: "${row.outputs.en}"`) : null,
        row.outputs.my ? h('div', { class: 'text-cyan-300' }, `MY: "${row.outputs.my}"`) : null,
      ])
    },
  },
  {
    title: 'Masked Myanmar Variants',
    key: 'variants_my',
    render(row: PolicyConcept) {
      if (!row.variants_my.length) return h('span', { class: 'text-gray-600 text-xs' }, 'None')
      return h(
        'div',
        { class: 'flex flex-wrap gap-1' },
        row.variants_my.map((v) =>
          h(
            NTag,
            { size: 'tiny', bordered: false, class: 'bg-gray-800 text-gray-200 text-[11px]' },
            { default: () => v }
          )
        )
      )
    },
  },
  {
    title: 'Masked English Variants',
    key: 'variants_en',
    render(row: PolicyConcept) {
      if (!row.variants_en.length) return h('span', { class: 'text-gray-600 text-xs' }, 'None')
      return h(
        'div',
        { class: 'flex flex-wrap gap-1' },
        row.variants_en.map((v) =>
          h(
            NTag,
            { size: 'tiny', bordered: false, class: 'bg-gray-800/80 text-gray-300 font-mono text-[10px]' },
            { default: () => v }
          )
        )
      )
    },
  },
]
</script>

<template>
  <div class="space-y-6 max-w-7xl mx-auto">
    <!-- Header -->
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
      <div>
        <div class="flex items-center space-x-2">
          <h1 class="text-2xl font-bold text-gray-100 tracking-tight">Term Policy & Sensitive Glossary</h1>
          <NTag size="small" type="success" class="text-[10px] font-mono">
            {{ policyStore.policy?.version ? `v${policyStore.policy.version}` : 'v1' }} ACTIVE
          </NTag>
        </div>
        <p class="text-xs text-gray-400 mt-0.5">
          Zero-Gaming terminology dictionary, pre-translation placeholder masking, and Layer 3 deny-scan filters.
        </p>
      </div>
      <div class="flex items-center space-x-3">
        <NButton type="primary" size="small" @click="handleRunRegression" :loading="runningRegression">
          <template #icon>
            <PlayCircleOutline />
          </template>
          Run 40-Case Regression Suite
        </NButton>
        <NButton secondary size="small" @click="policyStore.fetchPolicy" :loading="policyStore.loading">
          <template #icon>
            <RefreshOutline />
          </template>
          Refresh Policy
        </NButton>
      </div>
    </div>

    <!-- 4 Stats Cards -->
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
      <NCard class="glass-panel border-gray-800 rounded-xl" :bordered="false">
        <div class="text-xs text-gray-400">Protected Concepts</div>
        <div class="text-2xl font-bold text-cyan-400 font-mono mt-1">{{ stats.concepts }}</div>
        <div class="text-[11px] text-gray-500 mt-1">Platform, Deposit, User ID, etc.</div>
      </NCard>

      <NCard class="glass-panel border-gray-800 rounded-xl" :bordered="false">
        <div class="text-xs text-gray-400">Myanmar Word Variants</div>
        <div class="text-2xl font-bold text-emerald-400 font-mono mt-1">{{ stats.myVariants }}</div>
        <div class="text-[11px] text-gray-500 mt-1">Longest-match-first masked</div>
      </NCard>

      <NCard class="glass-panel border-gray-800 rounded-xl" :bordered="false">
        <div class="text-xs text-gray-400">English Word Variants</div>
        <div class="text-2xl font-bold text-indigo-400 font-mono mt-1">{{ stats.enVariants }}</div>
        <div class="text-[11px] text-gray-500 mt-1">Normalized regex boundary scans</div>
      </NCard>

      <NCard class="glass-panel border-gray-800 rounded-xl" :bordered="false">
        <div class="text-xs text-gray-400">Layer 3 Deny Words</div>
        <div class="text-2xl font-bold text-amber-400 font-mono mt-1">{{ stats.denyTerms }}</div>
        <div class="text-[11px] text-gray-500 mt-1">Separator evasion protected</div>
      </NCard>
    </div>

    <!-- Main Content Tabs -->
    <NSpin :show="policyStore.loading">
      <NCard class="glass-panel border-gray-800 rounded-xl" :bordered="false">
        <NTabs type="line" animated>
          <!-- Tab 1: Concepts Table -->
          <NTabPane name="concepts" tab="Protected Concepts (Layer 2 Masking)">
            <div class="space-y-4 pt-2">
              <div class="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4">
                <div class="w-full max-w-md">
                  <NInput
                    v-model:value="searchQuery"
                    placeholder="Search concept key, Myanmar term (e.g. ဂိမ်း), or English..."
                    size="small"
                    clearable
                  >
                    <template #prefix>
                      <SearchOutline class="w-4 h-4 text-gray-500 mr-1" />
                    </template>
                  </NInput>
                </div>
                <div class="text-xs text-gray-500">
                  Showing {{ filteredConcepts.length }} of {{ stats.concepts }} concepts
                </div>
              </div>

              <NDataTable
                :columns="columns"
                :data="filteredConcepts"
                :row-key="(row) => row.key"
                :pagination="{ pageSize: 10 }"
                :scroll-x="750"
              />
            </div>
          </NTabPane>

          <!-- Tab 2: Deny Terms -->
          <NTabPane name="deny" tab="Layer 3 Forbidden Output Terms (Deny Scan)">
            <div class="space-y-6 pt-2">
              <div class="p-3 rounded-lg bg-red-950/20 border border-red-800/40 text-xs text-red-200 flex items-start space-x-2">
                <AlertCircleOutline class="w-5 h-5 text-red-400 shrink-0 mt-0.5" />
                <div>
                  <strong>Layer 3 Protection:</strong> If the AI provider attempts to generate any of the following terms in the translated output (including separator evasion like <code>g-a-m-e</code> or spaces), the translation is blocked, retried with strict temperature, and withheld if it leaks again.
                </div>
              </div>

              <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                <!-- English Deny Terms -->
                <div class="space-y-2">
                  <div class="flex items-center justify-between">
                    <h3 class="text-sm font-semibold text-gray-200">English Forbidden Terms</h3>
                    <NButton size="tiny" secondary type="error" @click="openAddDenyModal('en')">
                      <template #icon><AddOutline /></template>
                      Add Term
                    </NButton>
                  </div>
                  <div class="p-4 rounded-xl bg-gray-900/80 border border-gray-800 flex flex-wrap gap-1.5 max-h-96 overflow-y-auto">
                    <NTag
                      v-for="term in policyStore.policy?.deny_terms?.en || []"
                      :key="term"
                      size="small"
                      type="error"
                      closable
                      class="font-mono text-xs cursor-pointer"
                      @close="handleDeleteDenyTerm('en', term)"
                    >
                      {{ term }}
                    </NTag>
                  </div>
                </div>

                <!-- Myanmar Deny Terms -->
                <div class="space-y-2">
                  <div class="flex items-center justify-between">
                    <h3 class="text-sm font-semibold text-gray-200">Myanmar Forbidden Terms</h3>
                    <NButton size="tiny" secondary type="error" @click="openAddDenyModal('my')">
                      <template #icon><AddOutline /></template>
                      Add Term
                    </NButton>
                  </div>
                  <div class="p-4 rounded-xl bg-gray-900/80 border border-gray-800 flex flex-wrap gap-1.5 max-h-96 overflow-y-auto">
                    <NTag
                      v-for="term in policyStore.policy?.deny_terms?.my || []"
                      :key="term"
                      size="small"
                      type="error"
                      closable
                      class="text-xs cursor-pointer"
                      @close="handleDeleteDenyTerm('my', term)"
                    >
                      {{ term }}
                    </NTag>
                  </div>
                </div>
              </div>
            </div>
          </NTabPane>

          <!-- Tab 3: Security Spec Architecture -->
          <NTabPane name="architecture" tab="Engine Defense Layers">
            <div class="space-y-4 pt-2 text-xs text-gray-300 leading-relaxed">
              <div class="p-4 rounded-xl bg-gray-900/80 border border-gray-800 space-y-3">
                <div class="flex items-center space-x-2 text-emerald-400 font-bold text-sm">
                  <ShieldCheckmarkOutline class="w-4 h-4" />
                  <span>Layer 1: Prompt Contract</span>
                </div>
                <p>
                  System prompt injects operational rules and neutral tone instructions. The LLM is instructed never to produce sensitive gaming terminology.
                </p>
              </div>

              <div class="p-4 rounded-xl bg-gray-900/80 border border-gray-800 space-y-3">
                <div class="flex items-center space-x-2 text-cyan-400 font-bold text-sm">
                  <ShieldCheckmarkOutline class="w-4 h-4" />
                  <span>Layer 2: Guaranteed Masking (Pre-flight)</span>
                </div>
                <p>
                  Sensitive terms are converted to Unicode placeholders like <code>⟦T:platform⟧</code> before leaving the server. The AI model cannot reproduce or leak terms it never received.
                </p>
              </div>

              <div class="p-4 rounded-xl bg-gray-900/80 border border-gray-800 space-y-3">
                <div class="flex items-center space-x-2 text-amber-400 font-bold text-sm">
                  <ShieldCheckmarkOutline class="w-4 h-4" />
                  <span>Layer 3: Verification & Sanitization (Post-flight)</span>
                </div>
                <p>
                  Returned outputs are checked against forbidden terms in the target language. Whitespace, hyphens, and zero-width characters are stripped to prevent evasion.
                </p>
              </div>
            </div>
          </NTabPane>
        </NTabs>
      </NCard>
    </NSpin>

    <!-- Regression Test Results Modal -->
    <NModal
      v-model:show="showRegressionModal"
      preset="card"
      title="Policy 40-Case Regression Test Results"
      class="max-w-2xl bg-gray-900 border border-gray-800"
      :bordered="false"
    >
      <div v-if="regressionResults" class="space-y-4">
        <div class="flex items-center justify-between p-3 rounded-lg bg-gray-800/60 border border-gray-700/50">
          <div class="flex items-center space-x-2">
            <CheckmarkCircleOutline v-if="regressionResults.ok" class="w-5 h-5 text-emerald-400" />
            <CloseCircleOutline v-else class="w-5 h-5 text-rose-400" />
            <span class="font-semibold text-sm text-gray-200">
              {{ regressionResults.ok ? 'All Regression Cases Passed' : 'Regression Failures Detected' }}
            </span>
          </div>
          <NTag :type="regressionResults.ok ? 'success' : 'error'" size="small">
            {{ regressionResults.passed }} / {{ regressionResults.total }} Passed
          </NTag>
        </div>

        <div class="max-h-96 overflow-y-auto space-y-2 pr-1">
          <div
            v-for="(problems, caseId) in regressionResults.results"
            :key="caseId"
            class="flex items-start justify-between p-2.5 rounded-lg bg-gray-950/50 border text-xs"
            :class="problems.length ? 'border-rose-900/50 text-rose-300' : 'border-gray-800/60 text-gray-300'"
          >
            <div class="font-mono font-medium">{{ caseId }}</div>
            <div v-if="!problems.length">
              <NTag size="tiny" type="success" :bordered="false">PASS</NTag>
            </div>
            <div v-else class="text-right text-rose-400">
              <span v-for="p in problems" :key="p">{{ p }}</span>
            </div>
          </div>
        </div>
      </div>
    </NModal>

    <!-- Add Forbidden Term Modal -->
    <NModal
      v-model:show="showAddDenyModal"
      preset="card"
      title="Add Forbidden Output Term (Layer 3)"
      class="max-w-md bg-gray-900 border border-gray-800"
      :bordered="false"
    >
      <NForm :model="denyForm" label-placement="top">
        <NFormItem label="Target Output Language" required>
          <NSelect v-model:value="denyForm.lang" :options="langOptions" />
        </NFormItem>
        <NFormItem label="Forbidden Word / Term" required>
          <NInput
            v-model:value="denyForm.term"
            placeholder="e.g. casino, slot, bonus"
            clearable
            @keyup.enter="handleAddDenyTerm"
          />
        </NFormItem>
        <div class="text-[11px] text-gray-400 bg-gray-800/40 p-2.5 rounded-lg mb-4 border border-gray-700/40">
          <strong class="text-amber-400">Safety Guard:</strong> Adding a term will automatically run against the 40-case Regression Suite. If this term conflicts with approved legitimate output terms, the addition will be blocked.
        </div>
        <div class="flex justify-end space-x-2">
          <NButton @click="showAddDenyModal = false">Cancel</NButton>
          <NButton
            type="error"
            :loading="addingDenyTerm"
            @click="handleAddDenyTerm"
          >
            Add & Verify
          </NButton>
        </div>
      </NForm>
    </NModal>
  </div>
</template>

