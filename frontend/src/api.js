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
    throw new Error(body.error?.message || `${res.status} ${res.statusText}`)
  }
  return res.json()
}
