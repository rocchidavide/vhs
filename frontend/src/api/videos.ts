import { currentLocale, t, te } from '@/i18n'

import { api } from './client'
import type { CollectionRef, TagRef } from './organization'

export type PlaybackStatus = 'ready' | 'preparing' | 'unavailable'

export interface Preparation {
  id: number
  kind: 'remux' | 'transcode'
  status: 'queued' | 'running' | 'completed' | 'failed'
  progress: number | null
  error_code: string
  error_message: string
  created_at: string
  completed_at: string | null
}

/** Why direct playback is not possible: a stable code plus its parameters (e.g. codec). */
export interface PlaybackIssue {
  code: string
  [parameter: string]: string
}

export interface Playback {
  status: PlaybackStatus
  source: 'original' | 'derived' | null
  action: '' | 'native' | 'remux' | 'transcode' | 'unsupported'
  issues: PlaybackIssue[]
  /** English diagnostic detail (older analyses may hold Italian text). */
  reason: string
  can_prepare: boolean
  preparation: Preparation | null
}

export interface Video {
  id: number
  title: string
  description: string
  platform: string
  platform_id: string
  source_url: string
  channel_name: string | null
  /** The broadcaster, for platforms whose channel is a series (RaiPlay). */
  network: string | null
  duration: number | null
  upload_date: string | null
  local_status: 'absent' | 'available' | 'missing'
  thumbnail: string | null
  source_status: 'unknown' | 'available' | 'unavailable' | 'deleted'
  container: string
  video_codec: string
  audio_codec: string
  resolution: string
  /** BCP 47 language of the archived audio track, '' when unknown. */
  audio_language: string
  audio_kind: AudioKind
  file_size: number | null
  playback: Playback
  tags: TagRef[]
  collections: CollectionRef[]
  /** Platform metadata, read-only: never personal tags. */
  source_tags: string[]
}

export interface VideoListItem {
  id: number
  title: string
  channel_id: number | null
  channel_name: string | null
  duration: number | null
  upload_date: string | null
  created_at: string
  local_status: 'absent' | 'available' | 'missing'
  thumbnail: string | null
  playback_status: PlaybackStatus
  progress_position: number | null
  progress_duration: number | null
  tags: TagRef[]
}

export interface Channel {
  id: number
  name: string
  platform: string
  video_count: number
}

export interface Progress {
  position_seconds: number
  duration: number | null
  updated_at: string | null
}

export interface LibraryQuery {
  q?: string
  channel?: number | null
  tag?: number[]
  collection?: number | null
  local_status?: string
  playback?: PlaybackStatus | ''
  ordering?: string
  limit?: number
  offset?: number
}

interface Page<T> {
  items: T[]
  count: number
}

export const PLAYBACK_STATUSES: readonly PlaybackStatus[] = ['ready', 'preparing', 'unavailable']

export function playbackLabel(status: PlaybackStatus): string {
  return t(`playback.status.${status}`)
}

export type AudioKind = '' | 'original' | 'default' | 'dubbed' | 'description'

/** "Italian · dubbed": the archived audio track; null when nothing is known about it. */
export function audioTrackLabel(language: string, kind: AudioKind): string | null {
  const parts: string[] = []
  if (language) parts.push(languageName(language))
  if (kind) parts.push(t(`video.audioKind.${kind}`))
  return parts.length ? parts.join(' · ') : null
}

function languageName(code: string): string {
  try {
    return new Intl.DisplayNames([currentLocale()], { type: 'language' }).of(code) ?? code
  } catch {
    return code
  }
}

/** Library orderings: the API value and the translation key of its label. */
export const COLLECTION_ORDERING = { value: 'position', labelKey: 'library.ordering.position' }

export const ORDERINGS: { value: string; labelKey: string }[] = [
  { value: '-created_at', labelKey: 'library.ordering.recent' },
  { value: '-upload_date', labelKey: 'library.ordering.published' },
  { value: 'title', labelKey: 'library.ordering.title' },
  { value: 'duration', labelKey: 'library.ordering.duration' },
]

export function preparationLabel(playback: Playback): string {
  const preparation = playback.preparation
  if (playback.status !== 'preparing') return ''
  if (!preparation || !['queued', 'running'].includes(preparation.status)) {
    return t('playback.analyzing')
  }
  const kind = preparation.kind === 'remux' ? 'remux' : 'transcode'
  if (preparation.status === 'queued') return t(`playback.${kind}Queued`)
  if (preparation.progress == null) return t(`playback.${kind}Running`)
  return t(`playback.${kind}RunningPercent`, { percent: Math.round(preparation.progress) })
}

/**
 * Why the video does not play directly, from its issue codes. Analyses made before the codes
 * existed have none: a generic message from the action is shown instead.
 */
export function playbackMessage(playback: Playback): string {
  const known = playback.issues.filter((issue) => te(`playback.issue.${issue.code}`))
  if (known.length) {
    return known.map(({ code, ...parameters }) => t(`playback.issue.${code}`, parameters)).join(' ')
  }
  return te(`playback.action.${playback.action}`) ? t(`playback.action.${playback.action}`) : ''
}

function queryString(query: LibraryQuery): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (Array.isArray(value)) {
      value.forEach((item) => params.append(key, String(item)))
    } else if (value !== undefined && value !== null && value !== '') {
      params.set(key, String(value))
    }
  }
  return params.toString()
}

export const videosApi = {
  list: (query: LibraryQuery) => api.get<Page<VideoListItem>>(`/videos/?${queryString(query)}`),
  channels: () => api.get<Channel[]>('/channels/'),
  get: (id: number) => api.get<Video>(`/videos/${id}`),
  prepare: (id: number) => api.post<Preparation>(`/videos/${id}/playback/prepare`),
  setTags: (id: number, tagIds: number[]) =>
    api.put<TagRef[]>(`/videos/${id}/tags`, { tag_ids: tagIds }),
  getProgress: (id: number) => api.get<Progress>(`/videos/${id}/progress`),
  saveProgress: (id: number, positionSeconds: number, duration: number | null, keepalive = false) =>
    api.put<Progress>(
      `/videos/${id}/progress`,
      { position_seconds: positionSeconds, duration },
      { keepalive },
    ),
  // Served by Nginx through X-Accel-Redirect: the player needs the dev proxy or the stack.
  streamUrl: (id: number) => `/api/v1/videos/${id}/stream`,
}
