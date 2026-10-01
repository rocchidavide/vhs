import { currentLocale } from '@/i18n'

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null) {
    return '—'
  }
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let value = bytes
  let unit = 0
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024
    unit += 1
  }
  const digits = unit === 0 ? 0 : 1
  const number = new Intl.NumberFormat(currentLocale(), {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value)
  return `${number} ${units[unit]}`
}

export function formatSpeed(bytesPerSecond: number | null | undefined): string {
  return bytesPerSecond == null ? '—' : `${formatBytes(bytesPerSecond)}/s`
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null) {
    return '—'
  }
  const total = Math.round(seconds)
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const secs = total % 60
  const pad = (n: number) => n.toString().padStart(2, '0')
  return hours > 0 ? `${hours}:${pad(minutes)}:${pad(secs)}` : `${minutes}:${pad(secs)}`
}

export function minutesSince(iso: string | null): number | null {
  if (!iso) {
    return null
  }
  return Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 60000))
}

export function formatDateTime(iso: string | null): string {
  if (!iso) {
    return '—'
  }
  return new Intl.DateTimeFormat(currentLocale(), { dateStyle: 'short', timeStyle: 'short' }).format(
    new Date(iso),
  )
}
