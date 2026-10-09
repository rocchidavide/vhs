import { describe, expect, it } from 'vitest'

import { audioTrackLabel } from '../videos'

describe('audioTrackLabel', () => {
  it('names the language and says what kind of track it is', () => {
    expect(audioTrackLabel('it', 'dubbed')).toBe('Italian · dubbed')
    expect(audioTrackLabel('en-US', 'original')).toBe('American English · original')
  })

  it('shows what is known, and nothing when nothing is', () => {
    expect(audioTrackLabel('', 'original')).toBe('original')
    expect(audioTrackLabel('it', '')).toBe('Italian')
    expect(audioTrackLabel('', '')).toBeNull()
  })
})
