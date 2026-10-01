<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { TAG_COLORS, type Tag } from '@/api/organization'
import { suggestTags } from '@/composables/organization'

const props = defineProps<{ tags: Tag[]; assignedIds: number[]; busy?: boolean }>()
const emit = defineEmits<{ select: [tag: Tag]; create: [name: string, color: string] }>()

const { t } = useI18n()
const query = ref('')
const open = ref(false)
const highlighted = ref(0)

const suggestions = computed(() => suggestTags(props.tags, query.value, props.assignedIds))
const options = computed(() => [
  ...suggestions.value.matches.map((tag) => ({ kind: 'tag' as const, tag })),
  ...(suggestions.value.create ? [{ kind: 'create' as const, name: suggestions.value.create }] : []),
])
// New tags cycle through the palette, so consecutive tags get different colors.
const nextColor = computed(() => TAG_COLORS[props.tags.length % TAG_COLORS.length] ?? TAG_COLORS[0]!)

function choose(index: number) {
  const option = options.value[index]
  // The field stays enabled while saving, so focus is kept for the next tag.
  if (!option || props.busy) return
  if (option.kind === 'tag') emit('select', option.tag)
  else emit('create', option.name, nextColor.value)
  query.value = ''
  highlighted.value = 0
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'ArrowDown') {
    event.preventDefault()
    open.value = true
    highlighted.value = Math.min(highlighted.value + 1, options.value.length - 1)
  } else if (event.key === 'ArrowUp') {
    event.preventDefault()
    highlighted.value = Math.max(highlighted.value - 1, 0)
  } else if (event.key === 'Enter') {
    event.preventDefault()
    choose(highlighted.value)
  } else if (event.key === 'Escape') {
    open.value = false
  }
}
</script>

<template>
  <div class="picker" @focusout="open = false">
    <input
      v-model="query"
      type="text"
      :placeholder="t('tags.addPlaceholder')"
      :aria-label="t('tags.add')"
      :aria-busy="busy"
      autocomplete="off"
      @focus="open = true"
      @input="
        open = true;
        highlighted = 0
      "
      @keydown="onKeydown"
    />
    <ul v-if="open && query.trim() && options.length" class="menu" role="listbox">
      <li
        v-for="(option, index) in options"
        :key="option.kind === 'tag' ? option.tag.id : 'create'"
        role="option"
        :aria-selected="index === highlighted"
        :class="{ active: index === highlighted }"
        @mousedown.prevent="choose(index)"
        @mouseenter="highlighted = index"
      >
        <template v-if="option.kind === 'tag'">
          <span class="dot" :style="{ background: option.tag.color }"></span>
          {{ option.tag.name }}
        </template>
        <template v-else>
          <span class="dot" :style="{ background: nextColor }"></span>
          {{ t('tags.createOption', { name: option.name }) }}
        </template>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.picker {
  position: relative;
  max-width: 320px;
}

.picker input {
  width: 100%;
}

.menu {
  position: absolute;
  z-index: 10;
  top: calc(100% + 4px);
  right: 0;
  left: 0;
  margin: 0;
  padding: 0.25rem;
  list-style: none;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  box-shadow: 0 8px 24px rgb(0 0 0 / 0.4);
}

li {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.375rem 0.5rem;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.875rem;
}

li.active {
  background: var(--color-surface-hover);
}

.dot {
  width: 0.5rem;
  height: 0.5rem;
  border-radius: 50%;
}
</style>
