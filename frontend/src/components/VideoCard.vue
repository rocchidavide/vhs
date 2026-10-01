<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import { playbackLabel, type VideoListItem } from '@/api/videos'
import { formatDuration } from '@/composables/format'
import TagChip from '@/components/TagChip.vue'

const props = defineProps<{ video: VideoListItem }>()

const { t } = useI18n()
const thumbnailFailed = ref(false)
const watched = computed(() => {
  const position = props.video.progress_position
  const total = props.video.progress_duration ?? props.video.duration
  if (!position || !total) return 0
  return Math.min(100, Math.round((100 * position) / total))
})
</script>

<template>
  <RouterLink :to="{ name: 'video', params: { id: video.id } }" class="card">
    <div class="thumb">
      <img
        v-if="video.thumbnail && !thumbnailFailed"
        :src="video.thumbnail"
        alt=""
        loading="lazy"
        @error="thumbnailFailed = true"
      />
      <span v-if="video.duration" class="duration">{{ formatDuration(video.duration) }}</span>
      <span v-if="video.playback_status !== 'ready'" class="badge" :class="video.playback_status">
        {{ playbackLabel(video.playback_status) }}
      </span>
      <div v-if="watched" class="watched" :aria-label="t('video.watched', { percent: watched })">
        <div :style="{ width: `${watched}%` }"></div>
      </div>
    </div>
    <h3 :title="video.title">{{ video.title }}</h3>
    <p class="meta">
      {{ video.channel_name ?? t('common.unknownChannel') }}
      <template v-if="video.upload_date"> · {{ video.upload_date }}</template>
    </p>
    <div v-if="video.tags.length" class="tags">
      <TagChip v-for="tag in video.tags.slice(0, 3)" :key="tag.id" :tag="tag" small />
      <span v-if="video.tags.length > 3" class="more">+{{ video.tags.length - 3 }}</span>
    </div>
  </RouterLink>
</template>

<style scoped>
.card {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  min-width: 0;
}

.thumb {
  position: relative;
  aspect-ratio: 16 / 9;
  overflow: hidden;
  background: var(--color-surface-hover);
  border-radius: 8px;
}

.thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 0.2s ease;
}

.card:hover .thumb img {
  transform: scale(1.03);
}

.duration,
.badge {
  position: absolute;
  padding: 0.125rem 0.375rem;
  border-radius: 4px;
  font-size: 0.75rem;
  background: rgb(0 0 0 / 0.75);
}

.duration {
  right: 0.375rem;
  bottom: 0.5rem;
}

.badge {
  top: 0.375rem;
  left: 0.375rem;
}

.badge.unavailable {
  color: var(--color-danger);
}

.badge.preparing {
  color: var(--color-accent);
}

.watched {
  position: absolute;
  right: 0;
  bottom: 0;
  left: 0;
  height: 3px;
  background: rgb(255 255 255 / 0.2);
}

.watched div {
  height: 100%;
  background: var(--color-accent);
}

h3 {
  font-size: 0.9375rem;
  font-weight: 600;
  line-height: 1.3;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.card:hover h3 {
  color: var(--color-accent);
}

.meta {
  font-size: 0.8125rem;
  color: var(--color-text-muted);
}

.tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem;
  align-items: center;
}

.more {
  color: var(--color-text-muted);
  font-size: 0.6875rem;
}
</style>
