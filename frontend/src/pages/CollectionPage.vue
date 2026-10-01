<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute, useRouter } from 'vue-router'

import { ApiError } from '@/api/client'
import { collectionsApi, countLabel, type CollectionDetail } from '@/api/organization'
import { formatDuration } from '@/composables/format'
import { moveItem } from '@/composables/organization'
import { apiErrorMessage } from '@/i18n/errors'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const collection = ref<CollectionDetail | null>(null)
const error = ref<string | null>(null)
const actionError = ref<string | null>(null)
const busy = ref(false)
const editing = ref(false)
const form = ref({ name: '', description: '' })
const dragIndex = ref<number | null>(null)

const collectionId = computed(() => Number(route.params.id))

async function load(id: number) {
  error.value = null
  try {
    collection.value = await collectionsApi.get(id)
  } catch (err) {
    error.value =
      err instanceof ApiError && err.status === 404
        ? t('collections.notFound')
        : t('collections.loadOneFailed')
  }
}

async function run(action: () => Promise<CollectionDetail>) {
  busy.value = true
  actionError.value = null
  try {
    collection.value = await action()
  } catch (err) {
    actionError.value = apiErrorMessage(err, t('common.operationFailed'))
    await load(collectionId.value)
  } finally {
    busy.value = false
  }
}

function startEdit() {
  if (!collection.value) return
  form.value = { name: collection.value.name, description: collection.value.description }
  editing.value = true
}

async function saveEdit() {
  await run(() => collectionsApi.update(collectionId.value, form.value))
  if (!actionError.value) editing.value = false
}

// The new order is shown at once and saved; on failure the saved order is reloaded.
function move(from: number, to: number) {
  if (!collection.value || from === to) return
  const items = moveItem(collection.value.items, from, to)
  collection.value = { ...collection.value, items }
  run(() =>
    collectionsApi.reorder(
      collectionId.value,
      items.map((item) => item.video_id),
    ),
  )
}

function onDrop(index: number) {
  if (dragIndex.value !== null) move(dragIndex.value, index)
  dragIndex.value = null
}

const removeVideo = (videoId: number) =>
  run(() => collectionsApi.removeVideo(collectionId.value, videoId))
const setCover = (videoId: number) =>
  run(() => collectionsApi.update(collectionId.value, { cover_video_id: videoId }))
const clearCover = () => run(() => collectionsApi.update(collectionId.value, { clear_cover: true }))

async function removeCollection() {
  if (!collection.value) return
  const confirmed = window.confirm(
    t('collections.confirmDelete', { name: collection.value.name }),
  )
  if (!confirmed) return
  busy.value = true
  try {
    await collectionsApi.remove(collectionId.value)
    await router.push({ name: 'collections' })
  } catch (err) {
    actionError.value = apiErrorMessage(err, t('collections.deleteFailed'))
    busy.value = false
  }
}

watch(collectionId, load, { immediate: true })
</script>

<template>
  <p class="back"><RouterLink :to="{ name: 'collections' }">{{ t('collections.back') }}</RouterLink></p>
  <p v-if="error" class="error" role="alert">{{ error }}</p>

  <template v-else-if="collection">
    <header v-if="!editing" class="header">
      <div>
        <h1>{{ collection.name }}</h1>
        <p v-if="collection.description" class="description">{{ collection.description }}</p>
        <p class="meta">{{ countLabel(collection) }}</p>
      </div>
      <div class="actions">
        <RouterLink
          v-if="collection.archived_count"
          class="button-link"
          :to="{ name: 'library', query: { collection: String(collection.id) } }"
        >
          {{ t('collections.openInLibrary') }}
        </RouterLink>
        <button type="button" class="secondary" @click="startEdit">{{ t('common.edit') }}</button>
        <button type="button" class="danger" :disabled="busy" @click="removeCollection">
          {{ t('common.delete') }}
        </button>
      </div>
    </header>

    <form v-else class="edit" @submit.prevent="saveEdit">
      <label>
        {{ t('collections.name') }}
        <input v-model="form.name" type="text" maxlength="120" required />
      </label>
      <label>
        {{ t('collections.description') }}
        <textarea v-model="form.description" rows="3"></textarea>
      </label>
      <div class="actions">
        <button type="submit" :disabled="busy || !form.name.trim()">{{ t('common.save') }}</button>
        <button type="button" class="link-button" @click="editing = false">
          {{ t('common.cancel') }}
        </button>
      </div>
    </form>

    <p v-if="actionError" class="error" role="alert">{{ actionError }}</p>

    <p v-if="collection.items.length === 0" class="empty">
      {{ t('collections.emptyCollection') }}
    </p>
    <p v-else class="hint">{{ t('collections.reorderHint') }}</p>

    <ol class="items">
      <li
        v-for="(item, index) in collection.items"
        :key="item.video_id"
        class="item"
        :class="{ dragging: dragIndex === index }"
        draggable="true"
        @dragstart="dragIndex = index"
        @dragover.prevent
        @drop.prevent="onDrop(index)"
        @dragend="dragIndex = null"
      >
        <span class="handle" aria-hidden="true">⋮⋮</span>
        <span class="number">{{ index + 1 }}</span>
        <div class="thumb">
          <img v-if="item.thumbnail" :src="item.thumbnail" alt="" loading="lazy" />
        </div>
        <div class="info">
          <RouterLink
            v-if="item.local_status === 'available'"
            :to="{ name: 'video', params: { id: item.video_id } }"
            class="title"
          >
            {{ item.title }}
          </RouterLink>
          <span v-else class="title">{{ item.title }}</span>
          <p class="meta">
            {{ item.channel_name ?? t('common.unknownChannel') }} ·
            {{ formatDuration(item.duration) }}
            <span v-if="item.local_status !== 'available'" class="badge">
              {{ t('common.notArchived') }}
            </span>
            <span v-if="collection.cover_video_id === item.video_id" class="badge cover-badge">
              {{ t('collections.cover') }}
            </span>
          </p>
        </div>
        <div class="item-actions">
          <button
            type="button"
            class="icon"
            :disabled="busy || index === 0"
            :aria-label="t('collections.moveUp', { title: item.title })"
            @click="move(index, index - 1)"
          >
            ↑
          </button>
          <button
            type="button"
            class="icon"
            :disabled="busy || index === collection.items.length - 1"
            :aria-label="t('collections.moveDown', { title: item.title })"
            @click="move(index, index + 1)"
          >
            ↓
          </button>
          <button
            v-if="item.thumbnail && collection.cover_video_id !== item.video_id"
            type="button"
            class="link-button"
            :disabled="busy"
            @click="setCover(item.video_id)"
          >
            {{ t('collections.useAsCover') }}
          </button>
          <button
            v-else-if="collection.cover_video_id === item.video_id"
            type="button"
            class="link-button"
            :disabled="busy"
            @click="clearCover"
          >
            {{ t('collections.automaticCover') }}
          </button>
          <button
            type="button"
            class="link-button"
            :disabled="busy"
            @click="removeVideo(item.video_id)"
          >
            {{ t('common.remove') }}
          </button>
        </div>
      </li>
    </ol>
  </template>

  <p v-else class="meta">{{ t('common.loading') }}</p>
</template>

<style scoped>
.back a {
  color: var(--color-text-muted);
  font-size: 0.875rem;
}

.header,
.edit {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
  justify-content: space-between;
  align-items: flex-start;
  margin-top: 0.75rem;
}

.edit {
  flex-direction: column;
  max-width: 560px;
}

.edit label {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  width: 100%;
  color: var(--color-text-muted);
  font-size: 0.875rem;
}

textarea {
  padding: 0.5rem 0.75rem;
  background: var(--color-background);
  border: 1px solid var(--color-border);
  border-radius: 6px;
  color: var(--color-text);
  font: inherit;
  resize: vertical;
}

.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  align-items: center;
}

.description {
  margin-top: 0.375rem;
  white-space: pre-line;
  color: var(--color-text-muted);
}

.meta,
.hint,
.empty {
  color: var(--color-text-muted);
  font-size: 0.875rem;
}

.hint,
.empty {
  margin-top: 1.5rem;
}

.items {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin: 0.75rem 0 0;
  padding: 0;
  list-style: none;
}

.item {
  display: grid;
  grid-template-columns: auto auto 128px 1fr auto;
  gap: 0.75rem;
  align-items: center;
  padding: 0.5rem 0.75rem;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 10px;
}

.item.dragging {
  opacity: 0.5;
}

.handle {
  color: var(--color-text-muted);
  cursor: grab;
  letter-spacing: -0.2em;
}

.number {
  min-width: 1.5rem;
  color: var(--color-text-muted);
  font-variant-numeric: tabular-nums;
  text-align: right;
}

.thumb {
  aspect-ratio: 16 / 9;
  overflow: hidden;
  background: var(--color-surface-hover);
  border-radius: 6px;
}

.thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.info {
  min-width: 0;
}

.title {
  display: block;
  overflow: hidden;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

a.title:hover {
  color: var(--color-accent);
}

.badge {
  margin-left: 0.5rem;
  padding: 0 0.375rem;
  border: 1px solid var(--color-border);
  border-radius: 4px;
  font-size: 0.75rem;
}

.cover-badge {
  color: var(--color-accent);
}

.item-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  align-items: center;
  justify-content: flex-end;
}

.icon {
  padding: 0.25rem 0.5rem;
  background: var(--color-surface-hover);
  color: var(--color-text);
}

.secondary,
.button-link {
  padding: 0.5rem 1rem;
  background: var(--color-surface-hover);
  border-radius: 6px;
  color: var(--color-text);
  font-weight: 600;
}

.danger {
  background: transparent;
  border: 1px solid var(--color-danger);
  color: var(--color-danger);
}

.error {
  margin-top: 0.75rem;
  color: var(--color-danger);
}

@media (max-width: 720px) {
  .item {
    grid-template-columns: auto 96px 1fr;
  }

  .handle,
  .number {
    display: none;
  }

  .item-actions {
    grid-column: 1 / -1;
    justify-content: flex-start;
  }
}
</style>
