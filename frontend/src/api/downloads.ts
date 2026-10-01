import { t, te } from '@/i18n'

import { api } from './client'

export type DownloadStatus =
  | 'queued'
  | 'downloading'
  | 'processing'
  | 'completed'
  | 'failed'
  | 'cancelled'

export interface VideoSummary {
  id: number
  title: string
  platform: string
  platform_id: string
  channel_name: string | null
  /** Source metadata only: the UI never loads it (§22). */
  thumbnail_url: string
  /** Archived thumbnail served through protected media, null when there is no local copy. */
  thumbnail: string | null
  duration: number | null
  upload_date: string | null
  local_status: 'absent' | 'available' | 'missing'
  source_status: 'unknown' | 'available' | 'unavailable' | 'deleted'
}

export interface Download {
  id: number
  status: DownloadStatus
  progress: number | null
  downloaded_bytes: number | null
  total_bytes: number | null
  speed: number | null
  eta: number | null
  error_code: string
  error_message: string
  is_stalled: boolean
  created_at: string
  started_at: string | null
  completed_at: string | null
  last_progress_at: string | null
  last_heartbeat_at: string | null
  video: VideoSummary
}

interface Page<T> {
  items: T[]
  count: number
}

export const ACTIVE_STATUSES: readonly DownloadStatus[] = ['queued', 'downloading', 'processing']

export function statusLabel(status: DownloadStatus): string {
  return t(`downloads.status.${status}`)
}

/** Label for a download error_code; unknown codes read as an unexpected error. */
export function errorLabel(code: string): string {
  return te(`downloads.error.${code}`) ? t(`downloads.error.${code}`) : t('downloads.error.unknown')
}

export function isActive(download: Download): boolean {
  return ACTIVE_STATUSES.includes(download.status)
}

export const downloadsApi = {
  list: (limit = 50) => api.get<Page<Download>>(`/downloads/?limit=${limit}`),
  get: (id: number) => api.get<Download>(`/downloads/${id}`),
  create: (url: string) => api.post<Download>('/downloads/', { url }),
  retry: (id: number) => api.post<Download>(`/downloads/${id}/retry`),
}
