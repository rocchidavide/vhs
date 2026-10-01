<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import type { TagRef } from '@/api/organization'

defineProps<{ tag: TagRef; removable?: boolean; small?: boolean }>()
const emit = defineEmits<{ remove: [tag: TagRef] }>()
const { t } = useI18n()
</script>

<template>
  <span class="chip" :class="{ small }" :style="{ '--tag-color': tag.color }">
    <span class="dot" aria-hidden="true"></span>
    <span class="name">{{ tag.name }}</span>
    <button
      v-if="removable"
      type="button"
      class="remove"
      :aria-label="t('tags.removeTag', { name: tag.name })"
      @click.stop.prevent="emit('remove', tag)"
    >
      ×
    </button>
  </span>
</template>

<style scoped>
.chip {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  max-width: 100%;
  padding: 0.125rem 0.5rem;
  border: 1px solid color-mix(in srgb, var(--tag-color) 55%, transparent);
  border-radius: 999px;
  background: color-mix(in srgb, var(--tag-color) 16%, transparent);
  font-size: 0.8125rem;
  line-height: 1.5;
}

.chip.small {
  padding: 0 0.375rem;
  font-size: 0.6875rem;
}

.dot {
  flex-shrink: 0;
  width: 0.5rem;
  height: 0.5rem;
  border-radius: 50%;
  background: var(--tag-color);
}

.name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.remove {
  padding: 0 0.125rem;
  background: none;
  color: var(--color-text-muted);
  font-size: 1rem;
  line-height: 1;
}

.remove:hover {
  color: var(--color-text);
}
</style>
