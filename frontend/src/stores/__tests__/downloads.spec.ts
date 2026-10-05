import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { downloadsApi, type Download, type DownloadStatus } from '@/api/downloads'
import { POLL_INTERVAL_MS, useDownloadsStore } from '../downloads'

function download(id: number, status: DownloadStatus): Download {
  return {
    id,
    status,
    progress: null,
    downloaded_bytes: null,
    total_bytes: null,
    speed: null,
    eta: null,
    error_code: '',
    error_message: '',
    ytdlp_version: '',
    is_stalled: false,
    created_at: '2026-01-01T00:00:00Z',
    started_at: null,
    completed_at: null,
    last_progress_at: null,
    last_heartbeat_at: null,
    video: {
      id,
      title: `Video ${id}`,
      platform: 'youtube',
      platform_id: `id${id}`,
      channel_name: null,
      thumbnail_url: '',
      thumbnail: null,
      duration: null,
      upload_date: null,
      local_status: 'absent',
      source_status: 'available',
    },
  }
}

describe('downloads store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('polls while downloads are active and stops once they settle', async () => {
    const list = vi
      .spyOn(downloadsApi, 'list')
      .mockResolvedValueOnce({ items: [download(1, 'downloading')], count: 1 })
      .mockResolvedValueOnce({ items: [download(1, 'completed')], count: 1 })
    const store = useDownloadsStore()

    await store.startPolling()
    expect(store.active).toHaveLength(1)

    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)
    expect(store.history).toHaveLength(1)

    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3)
    expect(list).toHaveBeenCalledTimes(2)
    store.stopPolling()
  })

  it('does not poll when nothing is active', async () => {
    const list = vi
      .spyOn(downloadsApi, 'list')
      .mockResolvedValue({ items: [download(1, 'failed')], count: 1 })
    const store = useDownloadsStore()

    await store.startPolling()
    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3)

    expect(list).toHaveBeenCalledTimes(1)
    store.stopPolling()
  })

  it('adds a new download and starts polling', async () => {
    vi.spyOn(downloadsApi, 'list').mockResolvedValueOnce({ items: [], count: 0 })
    vi.spyOn(downloadsApi, 'create').mockResolvedValue(download(2, 'queued'))
    const store = useDownloadsStore()
    await store.startPolling()

    await store.create('https://youtu.be/abc')

    expect(store.active.map((item) => item.id)).toEqual([2])
    store.stopPolling()
  })
})
