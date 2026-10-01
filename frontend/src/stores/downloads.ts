import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { downloadsApi, isActive, type Download } from '@/api/downloads'

export const POLL_INTERVAL_MS = 2000

export const useDownloadsStore = defineStore('downloads', () => {
  const items = ref<Download[]>([])
  const loaded = ref(false)
  let timer: ReturnType<typeof setTimeout> | null = null
  let polling = false

  const active = computed(() => items.value.filter(isActive))
  const history = computed(() => items.value.filter((item) => !isActive(item)))

  async function refresh() {
    const page = await downloadsApi.list()
    items.value = page.items
    loaded.value = true
  }

  function upsert(download: Download) {
    const index = items.value.findIndex((item) => item.id === download.id)
    if (index === -1) {
      items.value = [download, ...items.value]
    } else {
      items.value.splice(index, 1, download)
    }
  }

  async function create(url: string) {
    const download = await downloadsApi.create(url)
    upsert(download)
    schedule()
    return download
  }

  async function retry(id: number) {
    const download = await downloadsApi.retry(id)
    upsert(download)
    schedule()
    return download
  }

  // Poll only while something is active; stop as soon as everything has settled.
  function schedule() {
    if (!polling || timer !== null || active.value.length === 0) {
      return
    }
    timer = setTimeout(async () => {
      timer = null
      try {
        await refresh()
      } finally {
        schedule()
      }
    }, POLL_INTERVAL_MS)
  }

  async function startPolling() {
    polling = true
    await refresh()
    schedule()
  }

  function stopPolling() {
    polling = false
    if (timer !== null) {
      clearTimeout(timer)
      timer = null
    }
  }

  return { items, loaded, active, history, refresh, create, retry, startPolling, stopPolling }
})
