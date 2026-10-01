<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRouter } from 'vue-router'

import { collectionsApi, countLabel, type Collection } from '@/api/organization'
import { apiErrorMessage } from '@/i18n/errors'

const router = useRouter()
const { t } = useI18n()
const collections = ref<Collection[]>([])
const loaded = ref(false)
const failed = ref(false)
const newName = ref('')
const creating = ref(false)
const createError = ref<string | null>(null)
const brokenCovers = ref(new Set<number>())

async function load() {
  try {
    collections.value = await collectionsApi.list()
  } catch {
    failed.value = true
  } finally {
    loaded.value = true
  }
}

async function create() {
  creating.value = true
  createError.value = null
  try {
    const collection = await collectionsApi.create(newName.value)
    await router.push({ name: 'collection', params: { id: collection.id } })
  } catch (err) {
    createError.value = apiErrorMessage(err, t('collections.createFailed'))
  } finally {
    creating.value = false
  }
}

onMounted(load)
</script>

<template>
  <h1>{{ t('collections.title') }}</h1>
  <p class="intro">{{ t('collections.intro') }}</p>

  <form class="create" @submit.prevent="create">
    <input
      v-model="newName"
      type="text"
      :placeholder="t('collections.newName')"
      :aria-label="t('collections.newName')"
      maxlength="120"
      :disabled="creating"
    />
    <button type="submit" :disabled="creating || !newName.trim()">
      {{ t('collections.create') }}
    </button>
  </form>
  <p v-if="createError" class="error" role="alert">{{ createError }}</p>

  <p v-if="failed" class="error" role="alert">{{ t('collections.loadFailed') }}</p>
  <p v-else-if="loaded && collections.length === 0" class="empty">
    {{ t('collections.empty') }}
  </p>

  <div class="grid">
    <RouterLink
      v-for="collection in collections"
      :key="collection.id"
      :to="{ name: 'collection', params: { id: collection.id } }"
      class="card"
    >
      <div class="cover">
        <img
          v-if="collection.cover && !brokenCovers.has(collection.id)"
          :src="collection.cover"
          alt=""
          loading="lazy"
          @error="brokenCovers.add(collection.id)"
        />
      </div>
      <h2>{{ collection.name }}</h2>
      <p class="meta">{{ countLabel(collection) }}</p>
    </RouterLink>
  </div>
</template>

<style scoped>
.intro {
  margin-top: 0.5rem;
  color: var(--color-text-muted);
}

.create {
  display: flex;
  gap: 0.75rem;
  max-width: 560px;
  margin-top: 1.5rem;
}

.create input {
  flex: 1;
  min-width: 0;
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 1.5rem 1rem;
  margin-top: 1.5rem;
}

.card {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}

.cover {
  aspect-ratio: 16 / 9;
  overflow: hidden;
  background: var(--color-surface-hover);
  border-radius: 8px;
}

.cover img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

h2 {
  font-size: 1rem;
}

.card:hover h2 {
  color: var(--color-accent);
}

.meta,
.empty {
  color: var(--color-text-muted);
  font-size: 0.875rem;
}

.empty {
  margin-top: 1.5rem;
}

.error {
  margin-top: 0.75rem;
  color: var(--color-danger);
}
</style>
