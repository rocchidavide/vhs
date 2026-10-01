import { ApiError } from '@/api/client'
import { t, te } from '@/i18n'

/**
 * Message for a failed API call: the translation of its stable code when there is one,
 * otherwise the server's own detail (e.g. a validation message), otherwise the fallback.
 */
export function apiErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    const code = error.code
    if (code && te(`apiErrors.${code}`)) return t(`apiErrors.${code}`)
    if (code && te(`downloads.error.${code}`)) return t(`downloads.error.${code}`)
    if (error.detail) return error.detail
  }
  return fallback
}
