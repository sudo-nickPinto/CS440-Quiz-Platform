// Auth0 errors that require an interactive sign-in.
export const NEEDS_INTERACTION = [
  'consent_required',
  'login_required',
  'interaction_required',
  'missing_refresh_token',
  'invalid_grant',
]

// The Auth0 email/password connection. Pinning it on interactive logins also
// hides Google on Auth0's hosted page.
export const PASSWORD_CONNECTION = 'Username-Password-Authentication'

// Set just before a user-started Auth0 redirect, so App can tell a failed
// sign-in apart from the silent session check (which should fail quietly).
const EXPLICIT_LOGIN = 'quiz-explicit-login'

export function markExplicitLogin() {
  try {
    sessionStorage.setItem(EXPLICIT_LOGIN, '1')
  } catch {
    // Without storage a failed sign-in just isn't explained.
  }
}

export function clearExplicitLogin() {
  try {
    sessionStorage.removeItem(EXPLICIT_LOGIN)
  } catch {
    // Nothing to clear without storage.
  }
}

export function wasExplicitLogin() {
  try {
    return sessionStorage.getItem(EXPLICIT_LOGIN) === '1'
  } catch {
    return false
  }
}

// Auth0 appState that brings the user back to the page they were on after a
// redirect sign-in. The root path needs no state; the app routes it already.
export function returnToState() {
  const { pathname, search } = window.location
  return pathname === '/' ? undefined : { returnTo: pathname + search }
}

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

  const contentType = response.headers.get('content-type') || ''
  const body = contentType.includes('text/csv')
    ? await response.text()
    : await response.json().catch(() => null)

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
