// Auth0 errors that require an interactive sign-in.
export const NEEDS_INTERACTION = [
  'consent_required',
  'login_required',
  'interaction_required',
  'missing_refresh_token',
  'invalid_grant',
]

// Calls the backend with the current user's Auth0 access token.
export async function apiFetch(path, getToken, options = {}) {
  const token = await getToken()
  const headers = new Headers(options.headers)

  headers.set('Authorization', `Bearer ${token}`)

  if (options.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  const base = import.meta.env.VITE_API_BASE_URL.replace(/\/+$/, '')

  const response = await fetch(`${base}${path}`, {
    ...options,
    headers,
  })

  const body = await response.json().catch(() => null)

  if (!response.ok) {
    const details = body?.error?.details

    const fields = Array.isArray(details)
      ? details
          .map((item) => `${(item.loc || []).join('.')}: ${item.msg}`)
          .join('; ')
      : ''

    const error = new Error(
      fields ||
      body?.error?.message ||
      `${response.status} ${response.statusText}`,
    )

    error.code = body?.error?.code
    error.status = response.status

    throw error
  }

  return body
}
