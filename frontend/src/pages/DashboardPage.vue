<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { healthApi, type Health } from '@/api/health'
import { systemApi, type SystemInfo } from '@/api/system'

const { t } = useI18n()
const health = ref<Health | null>(null)
const failed = ref(false)
const system = ref<SystemInfo | null>(null)

function version(value: string): string {
  return value || t('dashboard.unknownVersion')
}

onMounted(async () => {
  try {
    health.value = await healthApi.get()
  } catch {
    failed.value = true
  }
  try {
    system.value = await systemApi.info()
  } catch {
    // Versions are a convenience: the page works without them.
  }
})
</script>

<template>
  <h1>{{ t('dashboard.title') }}</h1>
  <section v-if="system?.update_available" class="panel update" role="status">
    <p>
      <strong>{{ t('dashboard.updateAvailable', { version: system.latest_version }) }}</strong>
      <a :href="system.latest_release_url ?? undefined" target="_blank" rel="noopener noreferrer">
        {{ t('dashboard.releaseNotes') }}
      </a>
    </p>
    <p class="hint">{{ t('dashboard.howToUpdate') }}</p>
  </section>
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
  <section v-if="system" class="panel">
    <h2>{{ t('dashboard.versionsTitle') }}</h2>
    <p class="status">
      {{
        t('dashboard.versions', {
          vhs: version(system.vhs_version),
          ytdlp: version(system.ytdlp_version),
          deno: version(system.deno_version),
        })
      }}
    </p>
    <p v-if="system.ytdlp_auto_update" class="status warning">
      {{ t('dashboard.ytdlpAutoUpdate') }}
    </p>
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

.update {
  border-color: var(--color-accent);
}

.update p {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  align-items: baseline;
}

.update a {
  color: var(--color-accent);
}

.hint {
  margin-top: 0.375rem;
  color: var(--color-text-muted);
  font-size: 0.875rem;
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

.status.warning {
  color: var(--color-accent);
}
</style>
