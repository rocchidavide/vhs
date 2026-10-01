import { currentLocale } from '@/i18n'

const API_BASE = '/api/v1'
const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS', 'TRACE'])

export interface ApiErrorBody {
  detail?: string
  code?: string
  video_id?: number
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
    public readonly body: ApiErrorBody = {},
  ) {
    super(detail)
    this.name = 'ApiError'
  }

  get code(): string | undefined {
    return this.body.code
  }
}

export function readCookie(name: string): string | null {
  const prefix = `${name}=`
  for (const part of document.cookie.split(';')) {
    const cookie = part.trim()
    if (cookie.startsWith(prefix)) {
      return decodeURIComponent(cookie.slice(prefix.length))
    }
  }
  return null
}

async function ensureCsrfToken(): Promise<string> {
  const token = readCookie('csrftoken')
  if (token) {
    return token
  }
  await fetch(`${API_BASE}/auth/csrf`, { credentials: 'same-origin' })
  return readCookie('csrftoken') ?? ''
}

export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? 'GET').toUpperCase()
  const headers = new Headers(init.headers)
  headers.set('Accept', 'application/json')
  // The API answers in the interface language, among those the backend offers.
  headers.set('Accept-Language', currentLocale())

  if (init.body !== undefined && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  if (!SAFE_METHODS.has(method)) {
    headers.set('X-CSRFToken', await ensureCsrfToken())
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    method,
    headers,
    credentials: 'same-origin',
  })

  if (!response.ok) {
    let detail = response.statusText
    let body: ApiErrorBody = {}
    try {
      body = await response.json()
      if (typeof body?.detail === 'string') {
        detail = body.detail
      }
    } catch {
      // response without a JSON body
    }
    throw new ApiError(response.status, detail, body)
  }

  if (response.status === 204) {
    return undefined as T
  }
  return (await response.json()) as T
}

export const api = {
  get: <T>(path: string) => apiRequest<T>(path),
  post: <T>(path: string, body?: unknown) =>
    apiRequest<T>(path, {
      method: 'POST',
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  // keepalive lets a request finish while the page is being hidden or closed.
  put: <T>(path: string, body: unknown, options: { keepalive?: boolean } = {}) =>
    apiRequest<T>(path, { method: 'PUT', body: JSON.stringify(body), ...options }),
  patch: <T>(path: string, body: unknown) =>
    apiRequest<T>(path, { method: 'PATCH', body: JSON.stringify(body) }),
  delete: <T>(path: string) => apiRequest<T>(path, { method: 'DELETE' }),
}
