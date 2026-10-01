import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError, api } from '../client'

function lastRequest(mock: ReturnType<typeof vi.fn<typeof fetch>>) {
  const [url, init = {}] = mock.mock.calls[mock.mock.calls.length - 1]!
  return { url, init }
}

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('api client', () => {
  const fetchMock = vi.fn<typeof fetch>()

  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock)
    document.cookie = 'csrftoken=test-token'
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    fetchMock.mockReset()
    document.cookie = 'csrftoken=; expires=Thu, 01 Jan 1970 00:00:00 GMT'
  })

  it('does not send the CSRF header on GET', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ status: 'ok' }))

    await api.get('/health')

    const { url, init } = lastRequest(fetchMock)
    expect(url).toBe('/api/v1/health')
    expect(init.credentials).toBe('same-origin')
    expect(new Headers(init.headers).has('X-CSRFToken')).toBe(false)
  })

  it('sends the CSRF token from the cookie on POST', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ id: 1 }))

    await api.post('/auth/login', { username: 'admin', password: 'secret' })

    const { init } = lastRequest(fetchMock)
    const headers = new Headers(init.headers)
    expect(init.method).toBe('POST')
    expect(headers.get('X-CSRFToken')).toBe('test-token')
    expect(headers.get('Content-Type')).toBe('application/json')
  })

  it('keeps the error body, e.g. already_archived with the video id', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ detail: 'Questo video è già archiviato.', code: 'already_archived', video_id: 7 }, 409),
    )

    const error = (await api.post('/downloads/', { url: 'x' }).catch((err) => err)) as ApiError

    expect(error).toBeInstanceOf(ApiError)
    expect(error.code).toBe('already_archived')
    expect(error.body.video_id).toBe(7)
  })

  it('raises ApiError with the detail of the response', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: 'Invalid credentials.' }, 401))

    const error = (await api.get('/auth/me').catch((err) => err)) as ApiError

    expect(error).toBeInstanceOf(ApiError)
    expect(error.status).toBe(401)
    expect(error.detail).toBe('Invalid credentials.')
  })
})
