<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { ApiError } from '@/api/client'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const { t } = useI18n()

const username = ref('')
const password = ref('')
const error = ref<string | null>(null)
const submitting = ref(false)

async function submit() {
  error.value = null
  submitting.value = true
  try {
    await auth.login(username.value, password.value)
    const next = typeof route.query.next === 'string' ? route.query.next : '/'
    await router.push(next.startsWith('/') ? next : '/')
  } catch (err) {
    error.value =
      err instanceof ApiError && err.status === 401
        ? t('login.invalid')
        : t('login.failed')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="login">
    <form class="card" @submit.prevent="submit">
      <h1>{{ t('app.name') }}</h1>
      <label>
        {{ t('login.username') }}
        <input v-model="username" autocomplete="username" required />
      </label>
      <label>
        {{ t('login.password') }}
        <input v-model="password" type="password" autocomplete="current-password" required />
      </label>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <button type="submit" :disabled="submitting">{{ t('login.submit') }}</button>
    </form>
  </div>
</template>

<style scoped>
.login {
  display: grid;
  place-items: center;
  min-height: 100vh;
  padding: 1rem;
}

.card {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  width: 100%;
  max-width: 340px;
  padding: 2rem;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 10px;
}

h1 {
  text-align: center;
  letter-spacing: 0.2em;
  color: var(--color-accent);
}

label {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  font-size: 0.875rem;
  color: var(--color-text-muted);
}

.error {
  color: var(--color-danger);
  font-size: 0.875rem;
}
</style>
