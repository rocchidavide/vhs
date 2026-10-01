import { t } from '@/i18n'

import { api } from './client'

export interface TagRef {
  id: number
  name: string
  slug: string
  color: string
}

export interface Tag extends TagRef {
  video_count: number
  archived_count: number
}

export interface CollectionRef {
  id: number
  name: string
}

export interface Collection {
  id: number
  name: string
  description: string
  cover_video_id: number | null
  cover: string | null
  video_count: number
  archived_count: number
  created_at: string
  updated_at: string
}

export interface CollectionItem {
  video_id: number
  position: number
  title: string
  channel_name: string | null
  duration: number | null
  local_status: 'absent' | 'available' | 'missing'
  thumbnail: string | null
}

export interface CollectionDetail extends Collection {
  items: CollectionItem[]
}

/** Colors readable on the dark theme. */
export const TAG_COLORS = [
  '#e5a50a',
  '#f06a6a',
  '#4cc38a',
  '#5aa9f0',
  '#b58af0',
  '#f08ac2',
  '#3cc6c6',
  '#9a9daa',
]

/** "12 videos, 10 archived", or just "12 videos" when every video is archived. */
export function countLabel(item: { video_count: number; archived_count: number }): string {
  const total = t('common.videoCount', { n: item.video_count }, item.video_count)
  return item.archived_count === item.video_count
    ? total
    : t('common.videoCountArchived', { total, n: item.archived_count })
}

export const tagsApi = {
  list: () => api.get<Tag[]>('/tags/'),
  create: (name: string, color: string) => api.post<Tag>('/tags/', { name, color }),
  update: (id: number, changes: { name?: string; color?: string }) =>
    api.patch<Tag>(`/tags/${id}`, changes),
  remove: (id: number) => api.delete<void>(`/tags/${id}`),
}

export const collectionsApi = {
  list: () => api.get<Collection[]>('/collections/'),
  get: (id: number) => api.get<CollectionDetail>(`/collections/${id}`),
  create: (name: string, description = '') =>
    api.post<CollectionDetail>('/collections/', { name, description }),
  update: (
    id: number,
    changes: { name?: string; description?: string; cover_video_id?: number; clear_cover?: boolean },
  ) => api.patch<CollectionDetail>(`/collections/${id}`, changes),
  remove: (id: number) => api.delete<void>(`/collections/${id}`),
  addVideo: (id: number, videoId: number) =>
    api.post<CollectionDetail>(`/collections/${id}/videos`, { video_id: videoId }),
  removeVideo: (id: number, videoId: number) =>
    api.delete<CollectionDetail>(`/collections/${id}/videos/${videoId}`),
  reorder: (id: number, videoIds: number[]) =>
    api.put<CollectionDetail>(`/collections/${id}/videos/order`, { video_ids: videoIds }),
}
