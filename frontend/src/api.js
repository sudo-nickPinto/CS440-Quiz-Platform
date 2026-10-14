// Silent token errors that only an interactive Auth0 login can fix. On
// localhost Auth0 never skips the API consent screen, so a restored session
// hits consent_required until the user accepts it once.
export const NEEDS_INTERACTION = [
  'consent_required',
  'login_required',
  'interaction_required',
  // No refresh token stored, or Auth0 rejected it (expired or revoked).
  'missing_refresh_token',
  'invalid_grant',
]

// Calls the FastAPI backend with the user's Auth0 access token attached.
// getToken is getAccessTokenSilently from useAuth0().
export async function apiFetch(path, getToken, options = {}) {
  const token = await getToken()
  const res = await fetch(`${import.meta.env.VITE_API_BASE_URL}${path}`, {
    ...options,
    headers: {
      Authorization: `Bearer ${token}`,
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
    },
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    // Keep the backend's error code and the HTTP status so callers can react
    // to specific failures (e.g. email_not_verified) instead of parsing text.
    const err = new Error(body.error?.message || `${res.status} ${res.statusText}`)
    err.code = body.error?.code
    err.status = res.status
    throw err
  }
  return res.json()
}
