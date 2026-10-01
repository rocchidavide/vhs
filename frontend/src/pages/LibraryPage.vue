<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { collectionsApi, tagsApi, type Collection, type Tag } from '@/api/organization'
import {
  COLLECTION_ORDERING,
  ORDERINGS,
  PLAYBACK_STATUSES,
  playbackLabel,
  videosApi,
  type Channel,
  type LibraryQuery,
  type PlaybackStatus,
  type VideoListItem,
} from '@/api/videos'
import TagChip from '@/components/TagChip.vue'
import VideoCard from '@/components/VideoCard.vue'

const PAGE_SIZE = 24
const SEARCH_DEBOUNCE_MS = 300

const route = useRoute()
const router = useRouter()
const { t } = useI18n()

const videos = ref<VideoListItem[]>([])
const total = ref(0)
const channels = ref<Channel[]>([])
const allTags = ref<Tag[]>([])
const allCollections = ref<Collection[]>([])
const loading = ref(false)
const failed = ref(false)

// Filters live in the query string, so a filtered library can be bookmarked or shared.
const search = ref(String(route.query.q ?? ''))
const channel = ref(route.query.channel ? Number(route.query.channel) : null)
const playback = ref<PlaybackStatus | ''>((route.query.playback as PlaybackStatus) ?? '')
const selectedTags = ref<number[]>(
  ([] as unknown[]).concat(route.query.tag ?? []).map(Number).filter(Number.isFinite),
)
const collection = ref(route.query.collection ? Number(route.query.collection) : null)
// With a collection selected the default order is the collection's own.
const ordering = ref(
  String(route.query.ordering ?? (route.query.collection ? 'position' : '-created_at')),
)
const tagToAdd = ref('')

const orderings = computed(() => (collection.value ? [COLLECTION_ORDERING, ...ORDERINGS] : ORDERINGS))
const activeTags = computed(() => allTags.value.filter((tag) => selectedTags.value.includes(tag.id)))
const addableTags = computed(() => allTags.value.filter((tag) => !selectedTags.value.includes(tag.id)))
const defaultOrdering = computed(() => (collection.value ? 'position' : '-created_at'))
const filtered = computed(
  () =>
    Boolean(search.value || channel.value || playback.value || collection.value) ||
    selectedTags.value.length > 0,
)

let requestId = 0

function currentQuery(offset: number): LibraryQuery {
  return {
    q: search.value.trim(),
    channel: channel.value,
    tag: selectedTags.value,
    collection: collection.value,
    playback: playback.value,
    ordering: ordering.value,
    limit: PAGE_SIZE,
    offset,
  }
}

async function load(append = false) {
  const id = ++requestId
  loading.value = true
  failed.value = false
  try {
    const page = await videosApi.list(currentQuery(append ? videos.value.length : 0))
    if (id !== requestId) return
    videos.value = append ? [...videos.value, ...page.items] : page.items
    total.value = page.count
  } catch {
    if (id === requestId) failed.value = true
  } finally {
    if (id === requestId) loading.value = false
  }
}

function syncRoute() {
  const query: Record<string, string | string[]> = {}
  if (search.value.trim()) query.q = search.value.trim()
  if (channel.value) query.channel = String(channel.value)
  if (selectedTags.value.length) query.tag = selectedTags.value.map(String)
  if (collection.value) query.collection = String(collection.value)
  if (playback.value) query.playback = playback.value
  if (ordering.value !== defaultOrdering.value) query.ordering = ordering.value
  router.replace({ query })
}

let debounce: ReturnType<typeof setTimeout> | null = null
watch(search, () => {
  if (debounce) clearTimeout(debounce)
  debounce = setTimeout(() => {
    syncRoute()
    load()
  }, SEARCH_DEBOUNCE_MS)
})

watch(collection, (current, previous) => {
  // Switch to the collection order when a collection is picked, and back when cleared.
  if (current && !previous) ordering.value = 'position'
  else if (!current && ordering.value === 'position') ordering.value = '-created_at'
})

watch([channel, playback, ordering, collection, selectedTags], () => {
  syncRoute()
  load()
})

function addTagFilter() {
  const id = Number(tagToAdd.value)
  if (id && !selectedTags.value.includes(id)) selectedTags.value = [...selectedTags.value, id]
  tagToAdd.value = ''
}

function removeTagFilter(id: number) {
  selectedTags.value = selectedTags.value.filter((tagId) => tagId !== id)
}

onMounted(async () => {
  load()
  const [loadedChannels, loadedTags, loadedCollections] = await Promise.allSettled([
    videosApi.channels(),
    tagsApi.list(),
    collectionsApi.list(),
  ])
  if (loadedChannels.status === 'fulfilled') channels.value = loadedChannels.value
  if (loadedTags.status === 'fulfilled') allTags.value = loadedTags.value
  if (loadedCollections.status === 'fulfilled') allCollections.value = loadedCollections.value
})
</script>

<template>
  <h1>{{ t('library.title') }}</h1>

  <div class="filters">
    <label class="search">
      <span class="sr-only">{{ t('library.search') }}</span>
      <input v-model="search" type="search" :placeholder="t('library.searchPlaceholder')" />
    </label>
    <label>
      <span class="sr-only">{{ t('library.channel') }}</span>
      <select v-model="channel">
        <option :value="null">{{ t('library.allChannels') }}</option>
        <option v-for="item in channels" :key="item.id" :value="item.id">
          {{ item.name }} ({{ item.video_count }})
        </option>
      </select>
    </label>
    <label v-if="addableTags.length">
      <span class="sr-only">{{ t('library.personalTag') }}</span>
      <select v-model="tagToAdd" @change="addTagFilter">
        <option value="">{{ t('library.filterByTag') }}</option>
        <option v-for="tag in addableTags" :key="tag.id" :value="String(tag.id)">
          {{ tag.name }}
        </option>
      </select>
    </label>
    <label v-if="allCollections.length">
      <span class="sr-only">{{ t('library.collection') }}</span>
      <select v-model="collection">
        <option :value="null">{{ t('library.allCollections') }}</option>
        <option v-for="item in allCollections" :key="item.id" :value="item.id">
          {{ item.name }}
        </option>
      </select>
    </label>
    <label>
      <span class="sr-only">{{ t('library.playback') }}</span>
      <select v-model="playback">
        <option value="">{{ t('library.allStates') }}</option>
        <option v-for="status in PLAYBACK_STATUSES" :key="status" :value="status">
          {{ playbackLabel(status) }}
        </option>
      </select>
    </label>
    <label>
      <span class="sr-only">{{ t('library.orderBy') }}</span>
      <select v-model="ordering">
        <option v-for="option in orderings" :key="option.value" :value="option.value">
          {{ t(option.labelKey) }}
        </option>
      </select>
    </label>
  </div>

  <div v-if="activeTags.length" class="active-tags">
    <span class="label">{{ t('library.activeTags') }}</span>
    <TagChip
      v-for="tag in activeTags"
      :key="tag.id"
      :tag="tag"
      removable
      @remove="removeTagFilter(tag.id)"
    />
  </div>

  <p v-if="failed" class="error" role="alert">{{ t('library.loadFailed') }}</p>
  <p v-else-if="!loading && videos.length === 0" class="empty">
    {{ filtered ? t('library.noMatch') : t('library.empty') }}
  </p>

  <p v-if="total" class="count">{{ t('common.videoCount', { n: total }, total) }}</p>
  <div class="grid">
    <VideoCard v-for="video in videos" :key="video.id" :video="video" />
  </div>

  <div v-if="videos.length < total" class="more">
    <button type="button" :disabled="loading" @click="load(true)">
      {{ loading ? t('common.loading') : t('library.loadMore') }}
    </button>
  </div>
</template>

<style scoped>
.filters {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  margin-top: 1.5rem;
}

.search {
  flex: 1 1 280px;
}

.search input {
  width: 100%;
}

.active-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
  align-items: center;
  margin-top: 0.75rem;
}

.active-tags .label {
  color: var(--color-text-muted);
  font-size: 0.8125rem;
}

.count {
  margin-top: 1.25rem;
  color: var(--color-text-muted);
  font-size: 0.875rem;
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 1.5rem 1rem;
  margin-top: 0.75rem;
}

.more {
  display: flex;
  justify-content: center;
  margin-top: 2rem;
}

.empty,
.error {
  margin-top: 2rem;
  color: var(--color-text-muted);
}

.error {
  color: var(--color-danger);
}
</style>
