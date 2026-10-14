import { useEffect, useState } from 'react'
import { useAuth0 } from '@auth0/auth0-react'
import { apiFetch } from '../api'

// Silent token errors that only an interactive Auth0 login can fix. On
// localhost Auth0 never skips the API consent screen, so a restored session
// hits consent_required until the user accepts it once.
const NEEDS_INTERACTION = [
  'consent_required',
  'login_required',
  'interaction_required',
]
const REDIRECTED = 'quiz-interactive-login-tried'

// Loads the user's account from the backend, which creates it on first login,
// before showing the app. Everyone is a host/participant for now.
export default function AccountGate({ children }) {
  const { getAccessTokenSilently, loginWithRedirect } = useAuth0()
  const [ready, setReady] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    apiFetch('/me', getAccessTokenSilently)
      .then(() => {
        if (cancelled) return
        try {
          sessionStorage.removeItem(REDIRECTED)
        } catch {
          // Storage may be unavailable.
        }
        setReady(true)
      })
      .catch((err) => {
        if (cancelled) return
        let alreadyTried
        try {
          alreadyTried = Boolean(sessionStorage.getItem(REDIRECTED))
          if (!alreadyTried) sessionStorage.setItem(REDIRECTED, '1')
        } catch {
          // Without storage, fall through to showing the error.
          alreadyTried = true
        }

        // Only redirect once per tab so a persistent failure can't loop.
        if (NEEDS_INTERACTION.includes(err.error) && !alreadyTried) {
          void loginWithRedirect().catch(() => setError(err.message))
          return
        }
        setError(err.message)
      })
    return () => {
      cancelled = true
    }
  }, [getAccessTokenSilently, loginWithRedirect])

  if (error) return <p className="error" role="alert">{error}</p>
  if (!ready) return <p className="muted" role="status">Loading…</p>
  return children
}
