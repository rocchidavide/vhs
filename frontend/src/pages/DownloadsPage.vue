<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import { ApiError } from '@/api/client'
import DownloadItem from '@/components/DownloadItem.vue'
import { apiErrorMessage } from '@/i18n/errors'
import { useDownloadsStore } from '@/stores/downloads'

const store = useDownloadsStore()
const { t } = useI18n()

const url = ref('')
const submitting = ref(false)
const formError = ref<string | null>(null)
const notice = ref<string | null>(null)
const archivedVideoId = ref<number | null>(null)
const retrying = ref<number | null>(null)
const loadError = ref(false)

async function submit() {
  formError.value = null
  notice.value = null
  archivedVideoId.value = null
  submitting.value = true
  try {
    const before = store.items.length
    await store.create(url.value)
    notice.value =
      store.items.length > before ? t('downloads.added') : t('downloads.alreadyQueued')
    url.value = ''
  } catch (error) {
    if (error instanceof ApiError && error.code === 'already_archived') {
      notice.value = t('downloads.alreadyArchived')
      archivedVideoId.value = error.body.video_id ?? null
      url.value = ''
    } else {
      formError.value = apiErrorMessage(error, t('downloads.requestFailed'))
    }
  } finally {
    submitting.value = false
  }
}

async function retry(id: number) {
  retrying.value = id
  try {
    await store.retry(id)
  } catch (error) {
    formError.value = apiErrorMessage(error, t('downloads.retryFailed'))
  } finally {
    retrying.value = null
  }
}

onMounted(async () => {
  try {
    await store.startPolling()
  } catch {
    loadError.value = true
  }
})

onUnmounted(() => store.stopPolling())
</script>

<template>
  <h1>{{ t('downloads.title') }}</h1>

  <form class="add" @submit.prevent="submit">
    <label for="download-url" class="sr-only">{{ t('downloads.urlLabel') }}</label>
    <input
      id="download-url"
      v-model="url"
      type="url"
      :placeholder="t('downloads.urlPlaceholder')"
      required
      :disabled="submitting"
    />
    <button type="submit" :disabled="submitting || !url">
      {{ submitting ? t('downloads.checking') : t('downloads.submit') }}
    </button>
  </form>
  <p v-if="formError" class="form-error" role="alert">{{ formError }}</p>
  <p v-else-if="notice" class="notice" role="status">
    {{ notice }}
    <RouterLink v-if="archivedVideoId" :to="{ name: 'video', params: { id: archivedVideoId } }">
      {{ t('downloads.openVideo') }}
    </RouterLink>
  </p>

  <p v-if="loadError" class="form-error">{{ t('downloads.loadFailed') }}</p>

  <section>
    <h2>{{ t('downloads.inProgress') }}</h2>
    <p v-if="store.loaded && store.active.length === 0" class="empty">
      {{ t('downloads.noneInProgress') }}
    </p>
    <div class="list">
      <DownloadItem v-for="item in store.active" :key="item.id" :download="item" />
    </div>
  </section>

  <section>
    <h2>{{ t('downloads.history') }}</h2>
    <p v-if="store.loaded && store.history.length === 0" class="empty">
      {{ t('downloads.noHistory') }}
    </p>
    <div class="list">
      <DownloadItem
        v-for="item in store.history"
        :key="item.id"
        :download="item"
        :retrying="retrying === item.id"
        @retry="retry"
      />
    </div>
  </section>
</template>

<style scoped>
.add {
  display: flex;
  gap: 0.75rem;
  margin-top: 1.5rem;
  max-width: 720px;
}

.add input {
  flex: 1;
  min-width: 0;
}

.form-error {
  margin-top: 0.5rem;
  color: var(--color-danger);
  font-size: 0.875rem;
}

.notice {
  margin-top: 0.5rem;
  color: var(--color-text-muted);
  font-size: 0.875rem;
}

section {
  margin-top: 2rem;
}

.list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  margin-top: 0.75rem;
}

.empty {
  margin-top: 0.5rem;
  color: var(--color-text-muted);
}
</style>
