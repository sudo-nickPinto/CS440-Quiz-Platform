// Calls the FastAPI backend with the user's Auth0 access token attached.
// getToken is getAccessTokenSilently from useAuth0().
export async function apiFetch(path, getToken) {
  const token = await getToken()
  const res = await fetch(`${import.meta.env.VITE_API_BASE_URL}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}
