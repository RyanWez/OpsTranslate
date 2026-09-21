import { createRouter, createWebHistory, RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '../stores/auth'

import AppLayout from '../components/layout/AppLayout.vue'
import LoginView from '../views/LoginView.vue'
import OverviewView from '../views/OverviewView.vue'
import ProvidersView from '../views/ProvidersView.vue'
import UsersView from '../views/UsersView.vue'
import PlaygroundView from '../views/PlaygroundView.vue'
import LogsView from '../views/LogsView.vue'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: LoginView,
    meta: { guestOnly: true },
  },
  {
    path: '/',
    component: AppLayout,
    meta: { requiresAuth: true },
    children: [
      {
        path: '',
        name: 'overview',
        component: OverviewView,
      },
      {
        path: 'providers',
        name: 'providers',
        component: ProvidersView,
      },
      {
        path: 'users',
        name: 'users',
        component: UsersView,
      },
      {
        path: 'playground',
        name: 'playground',
        component: PlaygroundView,
      },
      {
        path: 'logs',
        name: 'logs',
        component: LogsView,
      },
    ],
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/',
  },
]

export const router = createRouter({
  history: createWebHistory('/admin/'),
  routes,
})

router.beforeEach(async (to, _from, next) => {
  const authStore = useAuthStore()

  if (!authStore.initialized) {
    await authStore.checkAuth()
  }

  if (to.meta.requiresAuth && !authStore.isAuthenticated) {
    return next({ name: 'login' })
  }

  if (to.meta.guestOnly && authStore.isAuthenticated) {
    return next({ name: 'overview' })
  }

  next()
})
