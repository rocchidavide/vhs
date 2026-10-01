<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { healthApi, type Health } from '@/api/health'

const { t } = useI18n()
const health = ref<Health | null>(null)
const failed = ref(false)

onMounted(async () => {
  try {
    health.value = await healthApi.get()
  } catch {
    failed.value = true
  }
})
</script>

<template>
  <h1>{{ t('dashboard.title') }}</h1>
  <section class="panel">
    <h2>{{ t('dashboard.systemStatus') }}</h2>
    <p v-if="failed" class="status error">{{ t('dashboard.unreachable') }}</p>
    <p v-else-if="health" class="status" :class="{ ok: health.status === 'ok' }">
      {{
        t('dashboard.status', {
          api: health.status,
          database: health.database,
          storage: health.storage,
        })
      }}
    </p>
    <p v-else class="status">{{ t('dashboard.checking') }}</p>
  </section>
</template>

<style scoped>
.panel {
  margin-top: 1.5rem;
  padding: 1.25rem;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 10px;
}

.status {
  margin-top: 0.5rem;
  color: var(--color-text-muted);
}

.status.ok {
  color: var(--color-success);
}

.status.error {
  color: var(--color-danger);
}
</style>
