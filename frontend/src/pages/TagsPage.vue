<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import { TAG_COLORS, countLabel, tagsApi, type Tag } from '@/api/organization'
import TagChip from '@/components/TagChip.vue'
import { apiErrorMessage } from '@/i18n/errors'

const { t } = useI18n()
const tags = ref<Tag[]>([])
const loaded = ref(false)
const error = ref<string | null>(null)
const editingId = ref<number | null>(null)
const form = ref({ name: '', color: TAG_COLORS[0]! })
const newTag = ref({ name: '', color: TAG_COLORS[0]! })
const busy = ref(false)

async function load() {
  try {
    tags.value = await tagsApi.list()
  } catch {
    error.value = t('tags.loadFailed')
  } finally {
    loaded.value = true
  }
}

async function run(action: () => Promise<unknown>) {
  busy.value = true
  error.value = null
  try {
    await action()
    await load()
    return true
  } catch (err) {
    error.value = apiErrorMessage(err, t('common.operationFailed'))
    return false
  } finally {
    busy.value = false
  }
}

async function create() {
  const created = await run(() => tagsApi.create(newTag.value.name, newTag.value.color))
  if (created) {
    const next = TAG_COLORS[tags.value.length % TAG_COLORS.length] ?? TAG_COLORS[0]!
    newTag.value = { name: '', color: next }
  }
}

function startEdit(tag: Tag) {
  editingId.value = tag.id
  form.value = { name: tag.name, color: tag.color }
}

async function save(tag: Tag) {
  if (await run(() => tagsApi.update(tag.id, form.value))) editingId.value = null
}

async function remove(tag: Tag) {
  const question = t('tags.confirmDelete', { name: tag.name })
  const effect = tag.video_count
    ? ` ${t('tags.deleteEffect', { n: tag.video_count }, tag.video_count)}`
    : ''
  const message = question + effect
  if (window.confirm(message)) await run(() => tagsApi.remove(tag.id))
}

onMounted(load)
</script>

<template>
  <h1>{{ t('tags.title') }}</h1>
  <p class="intro">{{ t('tags.intro') }}</p>

  <form class="row create" @submit.prevent="create">
    <input
      v-model="newTag.name"
      type="text"
      :placeholder="t('tags.newPlaceholder')"
      :aria-label="t('tags.newLabel')"
      maxlength="60"
      :disabled="busy"
    />
    <div class="swatches" role="radiogroup" :aria-label="t('tags.color')">
      <button
        v-for="color in TAG_COLORS"
        :key="color"
        type="button"
        class="swatch"
        :class="{ selected: newTag.color === color }"
        :style="{ background: color }"
        role="radio"
        :aria-checked="newTag.color === color"
        :aria-label="t('tags.colorOption', { color })"
        @click="newTag.color = color"
      ></button>
    </div>
    <button type="submit" :disabled="busy || !newTag.name.trim()">{{ t('common.create') }}</button>
  </form>

  <p v-if="error" class="error" role="alert">{{ error }}</p>
  <p v-if="loaded && tags.length === 0" class="empty">
    {{ t('tags.empty') }}
  </p>

  <ul class="tags">
    <li v-for="tag in tags" :key="tag.id" class="tag">
      <template v-if="editingId === tag.id">
        <form class="row" @submit.prevent="save(tag)">
          <input
            v-model="form.name"
            type="text"
            maxlength="60"
            :aria-label="t('tags.nameLabel')"
            required
          />
          <div class="swatches" role="radiogroup" :aria-label="t('tags.color')">
            <button
              v-for="color in TAG_COLORS"
              :key="color"
              type="button"
              class="swatch"
              :class="{ selected: form.color === color }"
              :style="{ background: color }"
              role="radio"
              :aria-checked="form.color === color"
              :aria-label="t('tags.colorOption', { color })"
              @click="form.color = color"
            ></button>
          </div>
          <button type="submit" :disabled="busy || !form.name.trim()">
            {{ t('common.save') }}
          </button>
          <button type="button" class="link-button" @click="editingId = null">
            {{ t('common.cancel') }}
          </button>
        </form>
      </template>
      <template v-else>
        <TagChip :tag="tag" />
        <RouterLink
          v-if="tag.archived_count"
          class="count"
          :to="{ name: 'library', query: { tag: String(tag.id) } }"
        >
          {{ countLabel(tag) }}
        </RouterLink>
        <span v-else class="count">{{ countLabel(tag) }}</span>
        <div class="tag-actions">
          <button type="button" class="link-button" :disabled="busy" @click="startEdit(tag)">
            {{ t('common.edit') }}
          </button>
          <button type="button" class="link-button danger" :disabled="busy" @click="remove(tag)">
            {{ t('common.delete') }}
          </button>
        </div>
      </template>
    </li>
  </ul>
</template>

<style scoped>
.intro {
  margin-top: 0.5rem;
  color: var(--color-text-muted);
}

.row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  align-items: center;
}

.create {
  margin-top: 1.5rem;
}

.create input {
  flex: 0 1 280px;
}

.swatches {
  display: flex;
  gap: 0.375rem;
}

.swatch {
  width: 1.375rem;
  height: 1.375rem;
  padding: 0;
  border: 2px solid transparent;
  border-radius: 50%;
}

.swatch.selected {
  border-color: var(--color-text);
}

.tags {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin: 1.5rem 0 0;
  padding: 0;
  list-style: none;
}

.tag {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
  align-items: center;
  padding: 0.625rem 0.75rem;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 10px;
}

.count {
  color: var(--color-text-muted);
  font-size: 0.875rem;
}

a.count:hover {
  color: var(--color-accent);
}

.tag-actions {
  display: flex;
  gap: 0.75rem;
  margin-left: auto;
}

.danger {
  color: var(--color-danger);
}

.empty {
  margin-top: 1.5rem;
  color: var(--color-text-muted);
}

.error {
  margin-top: 0.75rem;
  color: var(--color-danger);
}
</style>
