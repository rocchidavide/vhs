import { describe, expect, it } from 'vitest'

import { storageUsable, type Health } from '../health'

function health(storage: string): Health {
  return { status: 'ok', database: 'ok', storage, storage_message: '' }
}

describe('storageUsable', () => {
  it('accepts an initialized or brand-new library', () => {
    expect(storageUsable(health('ok'))).toBe(true)
    expect(storageUsable(health('new'))).toBe(true)
  })

  it('rejects every unavailable state', () => {
    for (const state of ['not_initialized', 'missing']) {
      expect(storageUsable(health(state))).toBe(false)
    }
  })
})
