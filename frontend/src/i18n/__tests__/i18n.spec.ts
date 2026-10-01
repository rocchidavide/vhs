import { describe, expect, it } from 'vitest'

import { ApiError } from '@/api/client'
import { errorLabel, statusLabel } from '@/api/downloads'
import { countLabel } from '@/api/organization'
import { playbackMessage, preparationLabel, type Playback } from '@/api/videos'
import { formatBytes } from '@/composables/format'
import { DEFAULT_LOCALE, detectLocale } from '@/i18n'
import { apiErrorMessage } from '@/i18n/errors'

function playback(overrides: Partial<Playback> = {}): Playback {
  return {
    status: 'unavailable',
    source: null,
    action: 'transcode',
    issues: [],
    reason: '',
    can_prepare: true,
    preparation: null,
    ...overrides,
  }
}

describe('detectLocale', () => {
  it('uses the first supported browser language, English otherwise', () => {
    expect(detectLocale(['en-GB', 'it'])).toBe('en')
    expect(detectLocale(['it-IT', 'it'])).toBe(DEFAULT_LOCALE)
    expect(detectLocale([])).toBe(DEFAULT_LOCALE)
  })
})

describe('apiErrorMessage', () => {
  it('translates stable codes and keeps the server detail for the others', () => {
    const duplicate = new ApiError(409, 'server text', { code: 'duplicate' })
    const invalid = new ApiError(422, 'The name can have at most 60 characters.', {
      code: 'invalid',
    })
    const download = new ApiError(422, 'Playlists are not supported yet.', { code: 'playlist' })

    expect(apiErrorMessage(duplicate, 'fallback')).toBe(
      'A personal tag with this name already exists.',
    )
    expect(apiErrorMessage(invalid, 'fallback')).toBe('The name can have at most 60 characters.')
    expect(apiErrorMessage(download, 'fallback')).toBe('Playlists and channels are not supported')
    expect(apiErrorMessage(new Error('boom'), 'fallback')).toBe('fallback')
  })
})

describe('playbackMessage', () => {
  it('builds the message from the issue codes and their parameters', () => {
    const message = playbackMessage(
      playback({
        issues: [
          { code: 'video_codec', codec: 'VP9' },
          { code: 'audio_codec', codec: 'Opus' },
        ],
      }),
    )
    expect(message).toBe(
      'VP9 video is not supported by every browser. Opus audio is not supported by every browser.',
    )
  })

  it('falls back to the action for analyses without codes (older ones)', () => {
    const older = playback({ issues: [], reason: 'Contenitore matroska non riproducibile' })
    expect(playbackMessage({ ...older, action: 'remux' })).toBe(
      'The container must be changed to MP4.',
    )
    expect(playbackMessage({ ...older, action: 'native', status: 'ready' })).toBe('')
  })

  it('ignores unknown codes', () => {
    const message = playbackMessage(playback({ issues: [{ code: 'from_the_future' }] }))
    expect(message).toBe('The video must be converted to play in the browser.')
  })
})

describe('labels', () => {
  it('translates statuses and error codes', () => {
    expect(statusLabel('downloading')).toBe('Downloading')
    expect(errorLabel('network')).toBe('Network error')
    expect(errorLabel('not_a_code')).toBe('Unexpected error')
  })

  it('pluralizes video counts', () => {
    expect(countLabel({ video_count: 1, archived_count: 1 })).toBe('1 video')
    expect(countLabel({ video_count: 12, archived_count: 12 })).toBe('12 videos')
    expect(countLabel({ video_count: 12, archived_count: 10 })).toBe('12 videos, 10 archived')
  })

  it('describes a running preparation with its progress', () => {
    const running = playback({
      status: 'preparing',
      preparation: {
        id: 1,
        kind: 'transcode',
        status: 'running',
        progress: 41.6,
        error_code: '',
        error_message: '',
        created_at: '',
        completed_at: null,
      },
    })
    expect(preparationLabel(running)).toBe('Converting (42%)…')
  })

  it('formats numbers for the interface language', () => {
    expect(formatBytes(1536)).toBe('1.5 KB')
    expect(formatBytes(512)).toBe('512 B')
  })
})
