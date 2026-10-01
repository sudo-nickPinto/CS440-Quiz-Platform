import { useEffect, useState } from 'react'
import { useAuth0 } from '@auth0/auth0-react'
import { apiFetch } from '../api'

// TEMPORARY: proves a real Auth0 token is accepted by the backend.
// Remove this file and its use in App.jsx once real API calls exist.
export default function BackendCheck() {
  const { getAccessTokenSilently } = useAuth0()
  const [status, setStatus] = useState('Checking backend…')
  useEffect(() => {
    apiFetch('/me', getAccessTokenSilently)
      .then((me) => setStatus(`Backend OK: signed in as ${me.sub}`))
      .catch((err) => setStatus(`Backend check failed: ${err.message}`))
  }, [getAccessTokenSilently])
  return <p className="muted" role="status">{status}</p>
}
