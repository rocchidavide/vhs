<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import type { Collection, CollectionRef } from '@/api/organization'

const props = defineProps<{ collections: Collection[]; memberOf: CollectionRef[]; busy?: boolean }>()
const emit = defineEmits<{ add: [collectionId: number]; create: [name: string] }>()

const { t } = useI18n()
const selected = ref<string>('')
const creating = ref(false)
const newName = ref('')

const available = computed(() =>
  props.collections.filter((item) => !props.memberOf.some((member) => member.id === item.id)),
)

function onSelect() {
  if (selected.value === '__new__') {
    creating.value = true
  } else if (selected.value) {
    emit('add', Number(selected.value))
  }
  selected.value = ''
}

function submitNew() {
  const name = newName.value.trim()
  if (!name) return
  emit('create', name)
  newName.value = ''
  creating.value = false
}
</script>

<template>
  <div class="picker">
    <form v-if="creating" class="new" @submit.prevent="submitNew">
      <input
        v-model="newName"
        type="text"
        :placeholder="t('collections.newName')"
        :aria-label="t('collections.newName')"
        maxlength="120"
        :disabled="busy"
      />
      <button type="submit" :disabled="busy || !newName.trim()">
        {{ t('collections.createAndAdd') }}
      </button>
      <button type="button" class="link-button" @click="creating = false">
        {{ t('common.cancel') }}
      </button>
    </form>
    <select
      v-else
      v-model="selected"
      :aria-label="t('collections.addTo')"
      :disabled="busy"
      @change="onSelect"
    >
      <option value="">{{ t('collections.addToPlaceholder') }}</option>
      <option v-for="item in available" :key="item.id" :value="String(item.id)">
        {{ item.name }}
      </option>
      <option value="__new__">{{ t('collections.newOption') }}</option>
    </select>
  </div>
</template>

<style scoped>
.new {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
}

.new input {
  flex: 1 1 220px;
}
</style>
