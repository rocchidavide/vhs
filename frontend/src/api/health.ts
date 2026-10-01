import { api } from './client'

export interface Health {
  status: 'ok' | 'degraded' | 'error'
  database: string
  /** ok | new | not_initialized | missing */
  storage: string
  storage_message: string
}

/** States in which the library can be used ("new" is created on the first download). */
export function storageUsable(health: Health): boolean {
  return health.storage === 'ok' || health.storage === 'new'
}

export const healthApi = {
  get: () => api.get<Health>('/health'),
}
