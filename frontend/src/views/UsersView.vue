<script setup lang="ts">
import { ref, onMounted, onUnmounted, h } from 'vue'
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
import { AddOutline, RefreshOutline, PersonCircleOutline } from '@vicons/ionicons5'
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

const showModal = ref(false)
const modalTitle = ref('Add Staff Member')
const isEditing = ref(false)
const formData = ref<UserPayload>({
  user_id: 0,
  display_name: '',
  role: 'staff',
  daily_soft_cap: 200,
  active: true,
})

function openAddModal() {
  isEditing.value = false
  modalTitle.value = 'Add Staff Member'
  formData.value = {
    user_id: 0,
    display_name: '',
    role: 'staff',
    daily_soft_cap: 200,
    active: true,
  }
  showModal.value = true
}

function openEditModal(row: StaffUser) {
  isEditing.value = true
  modalTitle.value = `Edit User: ${row.display_name || row.user_id}`
  formData.value = {
    user_id: row.user_id,
    display_name: row.display_name || '',
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

  try {
    const success = await usersStore.saveUser(formData.value)
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
    content: `Are you sure you want to revoke access for User ID ${row.user_id} (${row.display_name || 'Staff'})?`,
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
    title: 'Telegram User ID',
    key: 'user_id',
    render(row: StaffUser) {
      return h('div', { class: 'flex items-center space-x-2' }, [
        h(PersonCircleOutline, { class: 'w-4 h-4 text-gray-400' }),
        h('span', { class: 'font-mono text-xs font-semibold text-gray-200' }, row.user_id),
      ])
    },
  },
  {
    title: 'Display Name',
    key: 'display_name',
    render(row: StaffUser) {
      return h(
        'span',
        { class: 'text-sm text-gray-300' },
        row.display_name || '—'
      )
    },
  },
  {
    title: 'Role',
    key: 'role',
    width: 110,
    render(row: StaffUser) {
      const isAdmin = row.role === 'admin'
      return h(
        NTag,
        {
          size: 'small',
          type: isAdmin ? 'info' : 'success',
          class: 'uppercase font-mono text-[10px]',
        },
        { default: () => row.role }
      )
    },
  },
  {
    title: 'Daily Soft Cap',
    key: 'daily_soft_cap',
    width: 140,
    render(row: StaffUser) {
      return h('span', { class: 'font-mono text-xs text-gray-300' }, `${row.daily_soft_cap} msgs/day`)
    },
  },
  {
    title: 'Status',
    key: 'active',
    width: 110,
    render(row: StaffUser) {
      return h(
        NTag,
        {
          size: 'small',
          type: row.active ? 'success' : 'default',
          class: 'text-[11px]',
        },
        { default: () => (row.active ? 'Active' : 'Suspended') }
      )
    },
  },
  {
    title: 'Actions',
    key: 'actions',
    width: 150,
    render(row: StaffUser) {
      return h('div', { class: 'flex items-center space-x-2' }, [
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
        <h1 class="text-2xl font-bold text-gray-100 tracking-tight">Staff & Access Control</h1>
        <p class="text-xs text-gray-400 mt-0.5">Allowlist Telegram user IDs, manage roles, and enforce daily soft quota caps.</p>
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

    <!-- Table -->
    <NCard class="glass-panel border-gray-800 rounded-xl" :bordered="false">
      <NDataTable
        :columns="columns"
        :data="usersStore.users"
        :loading="usersStore.loading"
        :row-key="(row) => row.user_id"
        :scroll-x="700"
      />
    </NCard>

    <!-- Add/Edit Modal -->
    <NModal v-model:show="showModal" preset="card" :title="modalTitle" class="w-[94vw] max-w-md glass-panel border-gray-800 rounded-xl">
      <NForm label-placement="top" class="space-y-4">
        <NFormItem label="Telegram User ID" required>
          <NInputNumber
            v-model:value="formData.user_id"
            :disabled="isEditing"
            :show-button="false"
            placeholder="e.g. 123456789"
            class="w-full"
          />
        </NFormItem>

        <NFormItem label="Display Name / Note">
          <NInput v-model:value="formData.display_name" placeholder="e.g. John Doe (Support Lead)" />
        </NFormItem>

        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 sm:gap-4">
          <NFormItem label="Role" required>
            <NSelect v-model:value="formData.role" :options="roleOptions" />
          </NFormItem>
          <NFormItem label="Daily Soft Cap (Messages)" required>
            <NInputNumber v-model:value="formData.daily_soft_cap" :min="10" :max="5000" class="w-full" />
          </NFormItem>
        </div>

        <div class="flex items-center justify-between pt-2">
          <span class="text-xs text-gray-300">Grant Translation Access (Active)</span>
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
