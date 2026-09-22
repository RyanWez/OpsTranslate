<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, h } from 'vue'
import { useUsersStore } from '../stores/users'
import {
  NCard,
  NButton,
  NDataTable,
  NTag,
  NModal,
  NForm,
  NFormItem,
  NInput,
  NInputNumber,
  NSelect,
  NSwitch,
  useMessage,
  useDialog,
} from 'naive-ui'
import {
  AddOutline,
  RefreshOutline,
  SearchOutline,
  CopyOutline,
  OpenOutline,
} from '@vicons/ionicons5'
import type { StaffUser, UserPayload } from '../types'

const usersStore = useUsersStore()
const message = useMessage()
const dialog = useDialog()

onMounted(() => {
  usersStore.startLiveSync(4000)
})

onUnmounted(() => {
  usersStore.stopLiveSync()
})

const searchQuery = ref('')
const showModal = ref(false)
const modalTitle = ref('Add Staff Member')
const isEditing = ref(false)
const formData = ref<UserPayload>({
  user_id: 0,
  display_name: '',
  username: '',
  role: 'staff',
  daily_soft_cap: 200,
  active: true,
})

function formatRelativeTime(dateStr?: string | null): string {
  if (!dateStr) return 'Never'
  let normalized = dateStr
  if (!dateStr.endsWith('Z') && !dateStr.includes('+') && !dateStr.includes('T')) {
    normalized = dateStr.replace(' ', 'T') + 'Z'
  }
  const date = new Date(normalized)
  if (isNaN(date.getTime())) return 'Never'
  const now = new Date()
  const diffSec = Math.max(0, Math.floor((now.getTime() - date.getTime()) / 1000))
  if (diffSec < 60) return 'Just now'
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`
  if (diffSec < 86400 * 7) return `${Math.floor(diffSec / 86400)}d ago`
  return date.toLocaleDateString()
}

function copyToClipboard(text: string) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(() => {
      message.success(`Copied ID: ${text}`)
    }).catch(() => {
      message.info(`ID: ${text}`)
    })
  } else {
    message.info(`ID: ${text}`)
  }
}

const filteredUsers = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  if (!q) return usersStore.users
  return usersStore.users.filter((u) => {
    const nameMatch = u.display_name?.toLowerCase().includes(q)
    const userMatch = u.username?.toLowerCase().includes(q)
    const idMatch = String(u.user_id).includes(q)
    const roleMatch = u.role?.toLowerCase().includes(q)
    return nameMatch || userMatch || idMatch || roleMatch
  })
})

const activeCount = computed(() => usersStore.users.filter((u) => u.active).length)
const totalCount = computed(() => usersStore.users.length)

function openAddModal() {
  isEditing.value = false
  modalTitle.value = 'Add Staff Member'
  formData.value = {
    user_id: 0,
    display_name: '',
    username: '',
    role: 'staff',
    daily_soft_cap: 200,
    active: true,
  }
  showModal.value = true
}

function openEditModal(row: StaffUser) {
  isEditing.value = true
  modalTitle.value = `Edit User: ${row.display_name || row.username || row.user_id}`
  formData.value = {
    user_id: row.user_id,
    display_name: row.display_name || '',
    username: row.username ? row.username.replace(/^@/, '') : '',
    role: row.role,
    daily_soft_cap: row.daily_soft_cap,
    active: row.active,
  }
  showModal.value = true
}

async function handleSaveUser() {
  if (!formData.value.user_id) {
    message.warning('Please provide a valid Telegram User ID')
    return
  }

  // Sanitize username by stripping leading @
  const payload: UserPayload = {
    ...formData.value,
    username: formData.value.username ? formData.value.username.trim().replace(/^@/, '') : null,
  }

  try {
    const success = await usersStore.saveUser(payload)
    if (success) {
      message.success('User updated successfully')
      showModal.value = false
    }
  } catch (err: any) {
    message.error(err.response?.data?.detail || 'Failed to save user')
  }
}

function handleDeleteUser(row: StaffUser) {
  dialog.warning({
    title: 'Confirm Removal',
    content: `Are you sure you want to revoke access for User ID ${row.user_id} (${row.display_name || row.username || 'Staff'})?`,
    positiveText: 'Remove',
    negativeText: 'Cancel',
    onPositiveClick: async () => {
      try {
        await usersStore.deleteUser(row.user_id)
        message.success(`User ${row.user_id} removed`)
      } catch (err: any) {
        message.error(err.response?.data?.detail || 'Failed to remove user')
      }
    },
  })
}

const roleOptions = [
  { label: 'Staff (Standard translation quota)', value: 'staff' },
  { label: 'Admin (System management + elevated quota)', value: 'admin' },
]

const columns = [
  {
    title: 'Staff Member & Identity',
    key: 'identity',
    minWidth: 260,
    render(row: StaffUser) {
      const cleanUsername = row.username ? row.username.replace(/^@/, '') : null
      const initials = (row.display_name || (cleanUsername ? `@${cleanUsername}` : String(row.user_id)))
        .slice(0, 2)
        .toUpperCase()

      return h('div', { class: 'flex items-center space-x-3 py-1' }, [
        // Avatar circle
        h(
          'div',
          {
            class:
              'w-9 h-9 rounded-full bg-gradient-to-tr from-cyan-950 to-blue-900 border border-cyan-800/60 flex items-center justify-center text-cyan-300 font-semibold text-xs tracking-wider shrink-0 shadow-inner',
          },
          initials
        ),
        // Identity details
        h('div', { class: 'flex flex-col min-w-0' }, [
          // Display Name
          h(
            'div',
            { class: 'font-semibold text-sm text-gray-100 truncate' },
            row.display_name || 'Unnamed Member'
          ),
          // Username and ID row
          h('div', { class: 'flex items-center gap-2 text-xs flex-wrap mt-0.5' }, [
            cleanUsername
              ? h(
                  'a',
                  {
                    href: `https://t.me/${cleanUsername}`,
                    target: '_blank',
                    rel: 'noopener noreferrer',
                    class:
                      'inline-flex items-center text-cyan-400 hover:text-cyan-300 hover:underline font-mono text-[11px] transition-colors',
                  },
                  [
                    h('span', `@${cleanUsername}`),
                    h(OpenOutline, { class: 'w-3 h-3 ml-0.5 opacity-75' }),
                  ]
                )
              : null,
            h(
              'button',
              {
                type: 'button',
                onClick: () => copyToClipboard(String(row.user_id)),
                title: 'Click to copy Telegram User ID',
                class:
                  'inline-flex items-center text-gray-400 hover:text-gray-200 font-mono text-[11px] bg-gray-800/80 hover:bg-gray-700/80 px-1.5 py-0.5 rounded border border-gray-700/60 transition-colors',
              },
              [
                h('span', `ID: ${row.user_id}`),
                h(CopyOutline, { class: 'w-3 h-3 ml-1 opacity-70' }),
              ]
            ),
          ]),
        ]),
      ])
    },
  },
  {
    title: 'Role',
    key: 'role',
    width: 100,
    render(row: StaffUser) {
      const isAdmin = row.role === 'admin'
      return h(
        NTag,
        {
          size: 'small',
          type: isAdmin ? 'info' : 'default',
          class: 'uppercase font-mono text-[10px] tracking-wide font-semibold',
        },
        { default: () => row.role }
      )
    },
  },
  {
    title: 'Daily Cap',
    key: 'daily_soft_cap',
    width: 130,
    render(row: StaffUser) {
      return h('span', { class: 'font-mono text-xs text-gray-300' }, `${row.daily_soft_cap} msgs/day`)
    },
  },
  {
    title: 'Last Active',
    key: 'last_active_at',
    width: 130,
    render(row: StaffUser) {
      const relTime = formatRelativeTime(row.last_active_at)
      const isRecent = relTime.includes('now') || relTime.includes('m ago') || relTime.includes('h ago')
      return h(
        'span',
        {
          class: `text-xs font-mono ${isRecent ? 'text-cyan-400 font-medium' : 'text-gray-400'}`,
        },
        relTime
      )
    },
  },
  {
    title: 'Access Control',
    key: 'active',
    width: 130,
    render(row: StaffUser) {
      return h('div', { class: 'flex items-center space-x-2' }, [
        h(NSwitch, {
          size: 'small',
          value: row.active,
          onUpdateValue: async (val: boolean) => {
            const ok = await usersStore.toggleUserStatus(row.user_id, val)
            if (ok) {
              message.success(val ? `User ${row.user_id} activated` : `User ${row.user_id} suspended`)
            } else {
              message.error('Failed to update status')
            }
          },
        }),
        h(
          'span',
          {
            class: `text-[11px] font-medium ${row.active ? 'text-emerald-400' : 'text-gray-500'}`,
          },
          row.active ? 'Active' : 'Suspended'
        ),
      ])
    },
  },
  {
    title: 'Actions',
    key: 'actions',
    width: 130,
    render(row: StaffUser) {
      return h('div', { class: 'flex items-center space-x-1.5' }, [
        h(
          NButton,
          {
            size: 'tiny',
            secondary: true,
            onClick: () => openEditModal(row),
          },
          { default: () => 'Edit' }
        ),
        h(
          NButton,
          {
            size: 'tiny',
            quaternary: true,
            type: 'error',
            onClick: () => handleDeleteUser(row),
          },
          { default: () => 'Remove' }
        ),
      ])
    },
  },
]
</script>

<template>
  <div class="space-y-6 max-w-7xl mx-auto">
    <!-- Header -->
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
      <div>
        <div class="flex items-center gap-3">
          <h1 class="text-2xl font-bold text-gray-100 tracking-tight">Staff & Access Control</h1>
          <NTag size="small" :bordered="false" type="info" class="font-mono text-xs">
            {{ activeCount }} Active / {{ totalCount }} Total
          </NTag>
        </div>
        <p class="text-xs text-gray-400 mt-0.5">
          Allowlist Telegram user IDs, manage full names, usernames, roles, and auto-discovered members.
        </p>
      </div>
      <div class="flex items-center space-x-2 sm:space-x-3">
        <NButton secondary size="small" @click="() => usersStore.fetchUsers()" :loading="usersStore.loading">
          <template #icon>
            <RefreshOutline />
          </template>
          Refresh
        </NButton>
        <NButton type="primary" size="small" @click="openAddModal">
          <template #icon>
            <AddOutline />
          </template>
          Add Staff Member
        </NButton>
      </div>
    </div>

    <!-- Filter & Search Toolbar -->
    <div class="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
      <div class="w-full sm:max-w-md">
        <NInput
          v-model:value="searchQuery"
          clearable
          placeholder="Filter by Name, @username, or User ID..."
          size="small"
        >
          <template #prefix>
            <SearchOutline class="w-4 h-4 text-gray-400 mr-1" />
          </template>
        </NInput>
      </div>
    </div>

    <!-- Table -->
    <NCard class="glass-panel border-gray-800 rounded-xl overflow-hidden" :bordered="false">
      <NDataTable
        :columns="columns"
        :data="filteredUsers"
        :loading="usersStore.loading"
        :row-key="(row) => row.user_id"
        :scroll-x="850"
      />
    </NCard>

    <!-- Add/Edit Modal -->
    <NModal
      v-model:show="showModal"
      preset="card"
      :title="modalTitle"
      class="w-[94vw] max-w-md glass-panel border-gray-800 rounded-xl"
    >
      <NForm label-placement="top" class="space-y-4">
        <NFormItem label="Telegram User ID" required>
          <NInputNumber
            v-model:value="formData.user_id"
            :disabled="isEditing"
            :show-button="false"
            placeholder="e.g. 123456789"
            class="w-full font-mono"
          />
        </NFormItem>

        <NFormItem label="Full Display Name">
          <NInput v-model:value="formData.display_name" placeholder="e.g. John Doe" />
        </NFormItem>

        <NFormItem label="Telegram @Username (without @)">
          <NInput v-model:value="formData.username" placeholder="e.g. johndoe">
            <template #prefix>
              <span class="text-gray-500 text-xs">@</span>
            </template>
          </NInput>
        </NFormItem>

        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 sm:gap-4">
          <NFormItem label="Role" required>
            <NSelect v-model:value="formData.role" :options="roleOptions" />
          </NFormItem>
          <NFormItem label="Daily Soft Cap (Messages)" required>
            <NInputNumber v-model:value="formData.daily_soft_cap" :min="10" :max="5000" class="w-full" />
          </NFormItem>
        </div>

        <div class="flex items-center justify-between pt-2 border-t border-gray-800/60">
          <div>
            <div class="text-xs font-semibold text-gray-200">Grant Translation Access</div>
            <div class="text-[11px] text-gray-400">Allows bot usage and group message translation</div>
          </div>
          <NSwitch v-model:value="formData.active" />
        </div>

        <div class="flex justify-end space-x-3 pt-4 border-t border-gray-800/80">
          <NButton @click="showModal = false">Cancel</NButton>
          <NButton type="primary" :loading="usersStore.loading" @click="handleSaveUser">Save User</NButton>
        </div>
      </NForm>
    </NModal>
  </div>
</template>
