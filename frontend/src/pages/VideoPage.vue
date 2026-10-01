<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute } from 'vue-router'

import { ApiError } from '@/api/client'
import {
  collectionsApi,
  tagsApi,
  type Collection,
  type Tag,
  type TagRef,
} from '@/api/organization'
import {
  playbackLabel,
  playbackMessage,
  preparationLabel,
  videosApi,
  type Video,
} from '@/api/videos'
import CollectionPicker from '@/components/CollectionPicker.vue'
import TagChip from '@/components/TagChip.vue'
import TagPicker from '@/components/TagPicker.vue'
import { formatBytes, formatDuration } from '@/composables/format'
import { createProgressTracker, resumePosition } from '@/composables/playbackProgress'
import { apiErrorMessage } from '@/i18n/errors'

const POLL_INTERVAL_MS = 3000

const route = useRoute()
const { t } = useI18n()
const video = ref<Video | null>(null)
const error = ref<string | null>(null)
const playbackError = ref(false)
const preparing = ref(false)
const prepareError = ref<string | null>(null)
const player = ref<HTMLVideoElement | null>(null)

const videoId = computed(() => Number(route.params.id))
const playback = computed(() => video.value?.playback ?? null)
const ready = computed(() => playback.value?.status === 'ready')
// The stored reason is a diagnostic: shown for analyses without codes (older ones, possibly
// in another language) and for a failed analysis, where it carries the error.
const reasonDetail = computed(() => {
  const current = playback.value
  if (!current?.reason) return ''
  const withoutCodes = current.issues.length === 0
  const analysisFailed = current.issues.some((issue) => issue.code === 'analysis_failed')
  return withoutCodes || analysisFailed ? current.reason : ''
})
const sourceLabel = computed(() => {
  const source = playback.value?.source
  return source ? t(`playback.${source}`) : ''
})
const failedPreparation = computed(() => {
  const preparation = playback.value?.preparation
  return preparation?.status === 'failed' ? preparation : null
})

const allTags = ref<Tag[]>([])
const allCollections = ref<Collection[]>([])
const organizing = ref(false)
const organizeError = ref<string | null>(null)

async function loadOrganization() {
  try {
    ;[allTags.value, allCollections.value] = await Promise.all([
      tagsApi.list(),
      collectionsApi.list(),
    ])
  } catch {
    // The page still works without the pickers' suggestions.
  }
}

async function organize(action: () => Promise<unknown>) {
  organizing.value = true
  organizeError.value = null
  try {
    await action()
    video.value = await videosApi.get(videoId.value)
    await loadOrganization()
  } catch (err) {
    organizeError.value = apiErrorMessage(err, t('common.operationFailed'))
  } finally {
    organizing.value = false
  }
}

function tagIds(): number[] {
  return video.value?.tags.map((tag) => tag.id) ?? []
}

const addTag = (tag: TagRef) =>
  organize(() => videosApi.setTags(videoId.value, [...tagIds(), tag.id]))
const removeTag = (tag: TagRef) =>
  organize(() => videosApi.setTags(videoId.value, tagIds().filter((id) => id !== tag.id)))
const createTag = (name: string, color: string) =>
  organize(async () => {
    const tag = await tagsApi.create(name, color)
    await videosApi.setTags(videoId.value, [...tagIds(), tag.id])
  })
const addToCollection = (collectionId: number) =>
  organize(() => collectionsApi.addVideo(collectionId, videoId.value))
const createCollection = (name: string) =>
  organize(async () => {
    const collection = await collectionsApi.create(name)
    await collectionsApi.addVideo(collection.id, videoId.value)
  })
const removeFromCollection = (collectionId: number) =>
  organize(() => collectionsApi.removeVideo(collectionId, videoId.value))

let savedPosition = 0
const tracker = createProgressTracker((position, duration, keepalive) =>
  videosApi.saveProgress(videoId.value, position, duration, keepalive).catch(() => undefined),
)

let pollTimer: ReturnType<typeof setTimeout> | null = null

function stopPolling() {
  if (pollTimer) clearTimeout(pollTimer)
  pollTimer = null
}

// Poll while the browser copy is being prepared, then show the player.
function schedulePoll() {
  stopPolling()
  if (playback.value?.status !== 'preparing') return
  pollTimer = setTimeout(async () => {
    try {
      video.value = await videosApi.get(videoId.value)
    } finally {
      schedulePoll()
    }
  }, POLL_INTERVAL_MS)
}

async function load(id: number) {
  stopPolling()
  video.value = null
  error.value = null
  playbackError.value = false
  prepareError.value = null
  try {
    const [loaded, progress] = await Promise.all([
      videosApi.get(id),
      videosApi.getProgress(id).catch(() => null),
    ])
    video.value = loaded
    savedPosition = progress?.position_seconds ?? 0
    tracker.reset(savedPosition)
    schedulePoll()
  } catch (err) {
    error.value =
      err instanceof ApiError && err.status === 404
        ? t('video.notFound')
        : t('video.loadFailed')
  }
}

async function prepare() {
  preparing.value = true
  prepareError.value = null
  try {
    await videosApi.prepare(videoId.value)
    video.value = await videosApi.get(videoId.value)
    schedulePoll()
  } catch (err) {
    prepareError.value = apiErrorMessage(err, t('playback.prepareFailed'))
  } finally {
    preparing.value = false
  }
}

function onLoadedMetadata() {
  const element = player.value
  if (!element) return
  const start = resumePosition(savedPosition, element.duration)
  if (start !== null) element.currentTime = start
}

function onTimeUpdate() {
  const element = player.value
  if (element) tracker.update(element.currentTime, element.duration, !element.paused)
}

function onCheckpoint() {
  const element = player.value
  if (element) tracker.checkpoint(element.currentTime)
}

function onVisibilityChange() {
  if (document.visibilityState === 'hidden' && player.value) tracker.flush()
}

watch(videoId, load, { immediate: true })
onMounted(() => {
  document.addEventListener('visibilitychange', onVisibilityChange)
  loadOrganization()
})
onBeforeUnmount(() => {
  document.removeEventListener('visibilitychange', onVisibilityChange)
  stopPolling()
  if (player.value) tracker.flush()
})
</script>

<template>
  <p v-if="error" class="error" role="alert">{{ error }}</p>

  <article v-else-if="video && playback" class="video">
    <div v-if="ready" class="player">
      <video
        ref="player"
        :key="`${video.id}-${playback.source}`"
        :src="videosApi.streamUrl(video.id)"
        :poster="video.thumbnail ?? undefined"
        controls
        preload="metadata"
        playsinline
        @loadedmetadata="onLoadedMetadata"
        @timeupdate="onTimeUpdate"
        @pause="onCheckpoint"
        @seeked="onCheckpoint"
        @ended="onCheckpoint"
        @error="playbackError = true"
      ></video>
    </div>
    <div v-else class="placeholder" :class="playback.status">
      <img v-if="video.thumbnail" :src="video.thumbnail" alt="" />
      <div class="overlay">
        <p class="status-title">{{ playbackLabel(playback.status) }}</p>
        <p v-if="playback.status === 'preparing'">{{ preparationLabel(playback) }}</p>
        <template v-else>
          <p v-if="playbackMessage(playback)">{{ playbackMessage(playback) }}</p>
          <p v-if="reasonDetail" class="detail">{{ reasonDetail }}</p>
          <p v-if="failedPreparation" class="failure">
            {{ t('playback.lastAttemptFailed', { message: failedPreparation.error_message }) }}
          </p>
          <button v-if="playback.can_prepare" type="button" :disabled="preparing" @click="prepare">
            {{ failedPreparation ? t('playback.retryPreparation') : t('playback.prepare') }}
          </button>
          <p v-if="playback.can_prepare" class="hint">
            {{ t('playback.prepareHint') }}
          </p>
          <p v-if="prepareError" class="failure" role="alert">{{ prepareError }}</p>
        </template>
      </div>
    </div>
    <p v-if="playbackError" class="error" role="alert">
      {{ t('playback.playError') }}
    </p>

    <h1>{{ video.title }}</h1>
    <p class="meta">
      {{ video.channel_name ?? t('common.unknownChannel') }} ·
      {{ video.upload_date ?? t('common.unknownDate') }} · {{ formatDuration(video.duration) }}
    </p>
    <p class="meta playback-line">
      {{ t('playback.browserCopy') }}
      <strong :class="playback.status">{{ playbackLabel(playback.status) }}</strong>
      {{ sourceLabel }}
    </p>
    <p class="meta technical">
      {{ video.container || '—' }} · {{ video.video_codec || '—' }} ·
      {{ video.audio_codec || '—' }} · {{ video.resolution || '—' }} ·
      {{ formatBytes(video.file_size) }}
    </p>

    <section class="organize" aria-labelledby="personal-tags">
      <h2 id="personal-tags">{{ t('video.personalTags') }}</h2>
      <div class="chips">
        <TagChip v-for="tag in video.tags" :key="tag.id" :tag="tag" removable @remove="removeTag" />
        <span v-if="video.tags.length === 0" class="meta">{{ t('video.noPersonalTags') }}</span>
      </div>
      <TagPicker
        :tags="allTags"
        :assigned-ids="video.tags.map((tag) => tag.id)"
        :busy="organizing"
        @select="addTag"
        @create="createTag"
      />
    </section>

    <section class="organize" aria-labelledby="video-collections">
      <h2 id="video-collections">{{ t('video.collections') }}</h2>
      <ul v-if="video.collections.length" class="collections">
        <li v-for="collection in video.collections" :key="collection.id">
          <RouterLink :to="{ name: 'collection', params: { id: collection.id } }">
            {{ collection.name }}
          </RouterLink>
          <button
            type="button"
            class="link-button"
            :disabled="organizing"
            @click="removeFromCollection(collection.id)"
          >
            {{ t('common.remove') }}
          </button>
        </li>
      </ul>
      <p v-else class="meta">{{ t('video.notInCollection') }}</p>
      <CollectionPicker
        :collections="allCollections"
        :member-of="video.collections"
        :busy="organizing"
        @add="addToCollection"
        @create="createCollection"
      />
    </section>
    <p v-if="organizeError" class="error" role="alert">{{ organizeError }}</p>

    <p v-if="video.description" class="description">{{ video.description }}</p>

    <section v-if="video.source_tags.length" class="source-tags" aria-labelledby="source-tags">
      <h2 id="source-tags">{{ t('video.sourceTags') }}</h2>
      <p class="meta">{{ t('video.sourceTagsHint') }}</p>
      <p class="source-list">{{ video.source_tags.join(' · ') }}</p>
    </section>
  </article>

  <p v-else class="meta">{{ t('common.loading') }}</p>
</template>

<style scoped>
.video {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  max-width: 1100px;
}

.player video {
  display: block;
  width: 100%;
  max-height: 70vh;
  background: #000;
  border-radius: 10px;
}

.placeholder {
  position: relative;
  aspect-ratio: 16 / 9;
  max-height: 70vh;
  overflow: hidden;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 10px;
}

.placeholder img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  opacity: 0.25;
}

.overlay {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
  height: 100%;
  padding: 1.5rem;
  text-align: center;
  color: var(--color-text-muted);
}

.status-title {
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--color-text);
}

.preparing .status-title {
  color: var(--color-accent);
}

.failure {
  color: var(--color-danger);
  font-size: 0.875rem;
  overflow-wrap: anywhere;
}

/* Diagnostic detail stored with the analysis: secondary to the translated message. */
.detail {
  color: var(--color-text-muted);
  font-size: 0.8125rem;
  overflow-wrap: anywhere;
}

.hint {
  font-size: 0.8125rem;
}

.meta {
  color: var(--color-text-muted);
  font-size: 0.875rem;
}

.playback-line strong.ready {
  color: var(--color-success);
}

.playback-line strong.preparing {
  color: var(--color-accent);
}

.playback-line strong.unavailable {
  color: var(--color-danger);
}

.technical {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 0.8125rem;
}

.description {
  white-space: pre-line;
  color: var(--color-text-muted);
}

.error {
  color: var(--color-danger);
}

.organize,
.source-tags {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding-top: 0.75rem;
  border-top: 1px solid var(--color-border);
}

.organize h2,
.source-tags h2 {
  font-size: 1rem;
}

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
}

.collections {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.collections li {
  display: flex;
  gap: 0.75rem;
  align-items: baseline;
}

.collections a:hover {
  color: var(--color-accent);
}

.source-list {
  color: var(--color-text-muted);
  font-size: 0.875rem;
}
</style>
