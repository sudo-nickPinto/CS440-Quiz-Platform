import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { apiFetch, NEEDS_INTERACTION, returnToState } from './api.js'

function jsonResponse(status, body, statusText = '') {
  return new Response(JSON.stringify(body), {
    status,
    statusText,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('returnToState', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  function at(pathname, search = '') {
    vi.stubGlobal('window', { location: { pathname, search } })
  }

  it('needs no state on the home page', () => {
    at('/')
    expect(returnToState()).toBeUndefined()
  })

  it('remembers the page and its query string', () => {
    at('/app/classes/7', '?tab=students')
    expect(returnToState()).toEqual({ returnTo: '/app/classes/7?tab=students' })
  })

  it('brings a class invite link back after sign-in', () => {
    at('/app/join/class/ABCD-2345')
    expect(returnToState()).toEqual({ returnTo: '/app/join/class/ABCD-2345' })
  })
})

describe('NEEDS_INTERACTION', () => {
  it('includes the refresh-token failures that need a fresh sign-in', () => {
    expect(NEEDS_INTERACTION).toEqual(
      expect.arrayContaining([
        'login_required',
        'consent_required',
        'interaction_required',
        'missing_refresh_token',
        'invalid_grant',
      ]),
    )
  })
})

describe('apiFetch', () => {
  let fetchMock

  beforeEach(() => {
    vi.stubEnv('VITE_API_BASE_URL', 'https://api.test//')
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllEnvs()
    vi.unstubAllGlobals()
  })

  const getToken = () => Promise.resolve('token-123')

  it('sends the access token to the API base URL', async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, { account_id: 7 }))

    await expect(apiFetch('/me', getToken)).resolves.toEqual({ account_id: 7 })

    const [url, options] = fetchMock.mock.calls[0]
    expect(url).toBe('https://api.test/me')
    expect(options.headers.get('Authorization')).toBe('Bearer token-123')
    // A GET has no body, so no JSON content type.
    expect(options.headers.has('Content-Type')).toBe(false)
  })

  it('labels a body as JSON unless the caller chose a type', async () => {
    fetchMock.mockImplementation(() => Promise.resolve(jsonResponse(200, {})))

    await apiFetch('/classes/join', getToken, {
      method: 'POST',
      body: JSON.stringify({ code: 'ABCD2345' }),
    })
    await apiFetch('/upload', getToken, {
      method: 'POST',
      body: 'a,b',
      headers: { 'Content-Type': 'text/csv' },
    })

    const [first, second] = fetchMock.mock.calls.map(([, options]) => options)
    expect(first.method).toBe('POST')
    expect(first.body).toBe('{"code":"ABCD2345"}')
    expect(first.headers.get('Content-Type')).toBe('application/json')
    expect(second.headers.get('Content-Type')).toBe('text/csv')
    expect(second.headers.get('Authorization')).toBe('Bearer token-123')
  })

  it('turns the API error envelope into an error with code and status', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(403, {
        error: {
          code: 'email_not_verified',
          message: 'Please verify your email address, then log in again.',
        },
      }),
    )

    const error = await apiFetch('/me', getToken).catch((err) => err)

    expect(error).toBeInstanceOf(Error)
    expect(error.message).toBe(
      'Please verify your email address, then log in again.',
    )
    expect(error.code).toBe('email_not_verified')
    expect(error.status).toBe(403)
  })

  it('reports the deactivated-account refusal', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(403, {
        error: { code: 'inactive_account', message: 'This account is inactive.' },
      }),
    )

    await expect(apiFetch('/classes', getToken)).rejects.toMatchObject({
      code: 'inactive_account',
      status: 403,
    })
  })

  it('lists each invalid field from a validation error', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(422, {
        error: {
          code: 'validation_error',
          message: 'Request validation failed.',
          details: [
            { loc: ['body', 'name'], msg: 'Field required' },
            { loc: ['body', 'code'], msg: 'String should have at most 20 characters' },
          ],
        },
      }),
    )

    await expect(apiFetch('/classes', getToken)).rejects.toMatchObject({
      message:
        'body.name: Field required; ' +
        'body.code: String should have at most 20 characters',
      code: 'validation_error',
      status: 422,
    })
  })

  it('falls back to the HTTP status when the body is not JSON', async () => {
    fetchMock.mockResolvedValue(
      new Response('<html>proxy error</html>', {
        status: 502,
        statusText: 'Bad Gateway',
      }),
    )

    const error = await apiFetch('/me', getToken).catch((err) => err)

    expect(error.message).toBe('502 Bad Gateway')
    expect(error.code).toBeUndefined()
    expect(error.status).toBe(502)
  })

  it('passes a failed token refresh through untouched', async () => {
    // AccountGate reads err.error to decide whether to redirect to sign in.
    const refreshFailed = Object.assign(new Error('Missing Refresh Token'), {
      error: 'missing_refresh_token',
    })

    const error = await apiFetch('/me', () => Promise.reject(refreshFailed)).catch(
      (err) => err,
    )

    expect(error).toBe(refreshFailed)
    expect(NEEDS_INTERACTION).toContain(error.error)
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
