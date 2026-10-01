import { describe, expect, it, vi } from 'vitest'

import {
  SAVE_INTERVAL_MS,
  createProgressTracker,
  resumePosition,
  type SaveFn,
} from '../playbackProgress'

describe('resumePosition', () => {
  it('resumes from the middle of a video', () => {
    expect(resumePosition(60, 300)).toBe(60)
  })

  it('starts over near the beginning or the end', () => {
    expect(resumePosition(3, 300)).toBeNull()
    expect(resumePosition(295, 300)).toBeNull()
    expect(resumePosition(Number.NaN, 300)).toBeNull()
  })

  it('resumes when the duration is unknown', () => {
    expect(resumePosition(60, null)).toBe(60)
  })
})

describe('createProgressTracker', () => {
  function setup() {
    let clock = 0
    const save = vi.fn<SaveFn>()
    const tracker = createProgressTracker(save, () => clock)
    return { save, tracker, advance: (ms: number) => (clock += ms) }
  }

  it('saves at most every interval while playing', () => {
    const { save, tracker, advance } = setup()
    advance(SAVE_INTERVAL_MS)

    tracker.update(5, 300, true)
    advance(1000)
    tracker.update(6, 300, true)
    advance(SAVE_INTERVAL_MS)
    tracker.update(16, 300, true)

    expect(save.mock.calls).toEqual([
      [5, 300, false],
      [16, 300, false],
    ])
  })

  it('does not save while paused', () => {
    const { save, tracker, advance } = setup()
    advance(SAVE_INTERVAL_MS * 3)

    tracker.update(30, 300, false)

    expect(save).not.toHaveBeenCalled()
  })

  it('saves immediately on pause or seek, skipping unchanged positions', () => {
    const { save, tracker } = setup()
    tracker.reset(60)

    tracker.checkpoint(60.4)
    tracker.checkpoint(90)

    expect(save.mock.calls).toEqual([[90, null, false]])
  })

  it('flushes with keepalive when the page is hidden', () => {
    const { save, tracker } = setup()
    tracker.update(42, 300, false)

    tracker.flush()

    expect(save).toHaveBeenCalledWith(42, 300, true)
  })
})
