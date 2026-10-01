import { useEffect, useState } from 'react'
import { useAuth0 } from '@auth0/auth0-react'
import { apiFetch } from '../api'

// Loads the user's account from the backend, which creates it on first login,
// before showing the app. Everyone is a host/participant for now.
export default function AccountGate({ children }) {
  const { getAccessTokenSilently } = useAuth0()
  const [ready, setReady] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    apiFetch('/me', getAccessTokenSilently)
      .then(() => setReady(true))
      .catch((err) => setError(err.message))
  }, [getAccessTokenSilently])

  if (error) return <p className="error" role="alert">{error}</p>
  if (!ready) return <p className="muted" role="status">Loading…</p>
  return children
}
