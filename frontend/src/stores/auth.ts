import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { authApi, type User } from '@/api/auth'
import { ApiError } from '@/api/client'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(null)
  const checked = ref(false)

  const isAuthenticated = computed(() => user.value !== null)

  async function fetchMe() {
    try {
      user.value = await authApi.me()
    } catch (error) {
      if (!(error instanceof ApiError) || error.status !== 401) {
        throw error
      }
      user.value = null
    } finally {
      checked.value = true
    }
  }

  async function login(username: string, password: string) {
    user.value = await authApi.login(username, password)
    checked.value = true
  }

  async function logout() {
    await authApi.logout()
    user.value = null
  }

  return { user, checked, isAuthenticated, fetchMe, login, logout }
})
