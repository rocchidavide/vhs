<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'

import { healthApi, storageUsable, type Health } from '@/api/health'

const REFRESH_MS = 30_000

const { t, te } = useI18n()
const health = ref<Health | null>(null)
// Translated by state code; the server's message is only a fallback for an unknown state.
const message = computed(() => {
  const state = health.value?.storage ?? ''
  return te(`storage.state.${state}`) ? t(`storage.state.${state}`) : health.value?.storage_message
})
const route = useRoute()
let timer: ReturnType<typeof setInterval> | null = null

async function refresh() {
  try {
    health.value = await healthApi.get()
  } catch {
    // Backend unreachable: pages show their own errors.
  }
}

onMounted(() => {
  refresh()
  timer = setInterval(refresh, REFRESH_MS)
})
onUnmounted(() => {
  if (timer) clearInterval(timer)
})
watch(() => route.fullPath, refresh)
</script>

<template>
  <div v-if="health && !storageUsable(health)" class="banner" role="alert">
    <strong>{{ t('storage.unavailable') }}</strong>
    <span>{{ message }}</span>
    <span class="note">{{ t('storage.noWrites') }}</span>
  </div>
</template>

<style scoped>
.banner {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem 0.75rem;
  margin-bottom: 1.25rem;
  padding: 0.75rem 1rem;
  border: 1px solid var(--color-danger);
  border-radius: 8px;
  background: color-mix(in srgb, var(--color-danger) 12%, transparent);
  font-size: 0.875rem;
}

.note {
  color: var(--color-text-muted);
}
</style>
