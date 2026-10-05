<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import { errorLabel as labelForError, isActive, statusLabel, type Download } from '@/api/downloads'
import {
  formatBytes,
  formatDateTime,
  formatDuration,
  formatSpeed,
  minutesSince,
} from '@/composables/format'

const props = defineProps<{ download: Download; retrying?: boolean }>()
const emit = defineEmits<{ retry: [id: number] }>()

const { t } = useI18n()
const active = computed(() => isActive(props.download))
const percent = computed(() => Math.round(props.download.progress ?? 0))
const canRetry = computed(() => ['failed', 'cancelled'].includes(props.download.status))
const errorLabel = computed(() => labelForError(props.download.error_code))
// Local copy only; a placeholder until the video is archived or if the image fails.
const thumbnailFailed = ref(false)
watch(
  () => props.download.video.thumbnail,
  () => (thumbnailFailed.value = false),
)
const thumbnail = computed(() => (thumbnailFailed.value ? null : props.download.video.thumbnail))

const stalledMinutes = computed(() =>
  minutesSince(props.download.last_progress_at ?? props.download.started_at),
)
</script>

<template>
  <article class="item" :class="download.status">
    <img
      v-if="thumbnail"
      class="thumb"
      :src="thumbnail"
      alt=""
      loading="lazy"
      @error="thumbnailFailed = true"
    />
    <div v-else class="thumb placeholder" aria-hidden="true"></div>

    <div class="body">
      <div class="heading">
        <h3 :title="download.video.title">
          <RouterLink
            v-if="download.video.local_status === 'available'"
            :to="{ name: 'video', params: { id: download.video.id } }"
            class="title-link"
          >
            {{ download.video.title }}
          </RouterLink>
          <template v-else>{{ download.video.title }}</template>
        </h3>
        <span class="status">{{ statusLabel(download.status) }}</span>
      </div>
      <p class="meta">
        {{ download.video.channel_name ?? t('common.unknownChannel') }} ·
        {{ formatDuration(download.video.duration) }}
      </p>

      <template v-if="active">
        <div
          class="bar"
          role="progressbar"
          :aria-valuenow="percent"
          aria-valuemin="0"
          aria-valuemax="100"
          :aria-label="t('downloads.progressLabel', { title: download.video.title })"
        >
          <div class="fill" :style="{ width: `${percent}%` }"></div>
        </div>
        <p class="meta">
          <template v-if="download.status === 'downloading'">
            {{
              t('downloads.progress', {
                percent,
                done: formatBytes(download.downloaded_bytes),
                total: formatBytes(download.total_bytes),
                speed: formatSpeed(download.speed),
                eta: formatDuration(download.eta),
              })
            }}
          </template>
          <template v-else-if="download.status === 'processing'">
            {{ t('downloads.processing') }}
          </template>
          <template v-else>{{ t('downloads.waiting') }}</template>
        </p>
        <p v-if="download.is_stalled" class="warning">
          {{ t('downloads.stalled', { minutes: stalledMinutes }) }}
        </p>
      </template>

      <template v-else>
        <p class="meta">
          {{ formatDateTime(download.completed_at ?? download.created_at) }}
          <template v-if="download.status === 'completed'">
            · {{ formatBytes(download.total_bytes) }}
          </template>
        </p>
        <div v-if="download.status === 'failed'" class="error">
          <strong>{{ errorLabel }}</strong>
          <span v-if="download.error_message">{{ download.error_message }}</span>
          <span v-if="download.ytdlp_version" class="tool">
            {{ t('downloads.ytdlpVersion', { version: download.ytdlp_version }) }}
          </span>
        </div>
      </template>
    </div>

    <button
      v-if="canRetry"
      type="button"
      class="retry"
      :disabled="retrying"
      @click="emit('retry', download.id)"
    >
      {{ t('downloads.retry') }}
    </button>
  </article>
</template>

<style scoped>
.item {
  display: grid;
  grid-template-columns: 120px 1fr auto;
  gap: 1rem;
  align-items: start;
  padding: 1rem;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 10px;
}

.thumb {
  width: 120px;
  aspect-ratio: 16 / 9;
  object-fit: cover;
  border-radius: 6px;
  background: var(--color-surface-hover);
}

.body {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  min-width: 0;
}

.heading {
  display: flex;
  gap: 0.75rem;
  align-items: baseline;
  justify-content: space-between;
}

h3 {
  font-size: 1rem;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.title-link:hover {
  color: var(--color-accent);
}

.status {
  flex-shrink: 0;
  font-size: 0.75rem;
  color: var(--color-text-muted);
}

.completed .status {
  color: var(--color-success);
}

.failed .status {
  color: var(--color-danger);
}

.meta {
  font-size: 0.875rem;
  color: var(--color-text-muted);
}

.bar {
  height: 6px;
  overflow: hidden;
  background: var(--color-surface-hover);
  border-radius: 3px;
}

.fill {
  height: 100%;
  background: var(--color-accent);
  transition: width 0.4s ease;
}

.warning {
  font-size: 0.875rem;
  color: var(--color-accent);
}

.error {
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
  font-size: 0.875rem;
  color: var(--color-danger);
  overflow-wrap: anywhere;
}

.error span {
  color: var(--color-text-muted);
}

.error .tool {
  font-size: 0.75rem;
}

@media (max-width: 720px) {
  .item {
    grid-template-columns: 1fr;
  }

  .thumb {
    width: 100%;
  }
}
</style>
