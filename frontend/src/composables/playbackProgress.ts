/** Resume and periodic saving of the playback position (§13), independent of the DOM. */

export const SAVE_INTERVAL_MS = 10_000
export const MIN_RESUME_SECONDS = 5
export const END_MARGIN_SECONDS = 10
const MIN_CHANGE_SECONDS = 1

export type SaveFn = (position: number, duration: number | null, keepalive: boolean) => unknown

/** Where to start playing: resume only if the saved point is not at the very start or end. */
export function resumePosition(saved: number, duration: number | null): number | null {
  if (!Number.isFinite(saved) || saved < MIN_RESUME_SECONDS) return null
  if (duration && saved > duration - END_MARGIN_SECONDS) return null
  return saved
}

export function createProgressTracker(save: SaveFn, now: () => number = Date.now) {
  let lastSavedAt = 0
  let lastSavedPosition: number | null = null
  let position = 0
  let duration: number | null = null

  function persist(keepalive = false, force = false) {
    if (!force && lastSavedPosition !== null) {
      if (Math.abs(position - lastSavedPosition) < MIN_CHANGE_SECONDS) return
    }
    lastSavedAt = now()
    lastSavedPosition = position
    save(position, duration, keepalive)
  }

  return {
    /** Called on timeupdate: saves at most every SAVE_INTERVAL_MS while playing. */
    update(currentTime: number, total: number | null, playing: boolean) {
      position = currentTime
      duration = total && Number.isFinite(total) ? total : null
      if (playing && now() - lastSavedAt >= SAVE_INTERVAL_MS) persist()
    },
    /** Pause, seek or end: save right away. */
    checkpoint(currentTime: number) {
      position = currentTime
      persist()
    },
    /** Page hidden or left: save with keepalive so the request survives. */
    flush() {
      persist(true)
    },
    /** Mark the position already stored on the server (no save needed for it). */
    reset(savedPosition: number) {
      position = savedPosition
      lastSavedPosition = savedPosition
      lastSavedAt = now()
    },
  }
}
