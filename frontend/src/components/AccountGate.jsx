import { useEffect, useState } from 'react'
import { useAuth0 } from '@auth0/auth0-react'
import { apiFetch } from '../api'

const INTERACTIVE_ERRORS = [
  'consent_required',
  'login_required',
  'interaction_required',
]

export default function AccountGate({ children }) {
  const {
    getAccessTokenSilently,
    loginWithRedirect,
  } = useAuth0()

  const [ready, setReady] = useState(false)
  const [error, setError] = useState(null)
  const [redirecting, setRedirecting] = useState(false)

  useEffect(() => {
    let active = true

    apiFetch('/me', getAccessTokenSilently)
      .then(() => {
        if (!active) return
        setError(null)
        setReady(true)
      })
      .catch((err) => {
        if (!active) return
        setError({
          code: err.error,
          message: err.message || 'Could not load your account.',
        })
      })

    return () => {
      active = false
    }
  }, [getAccessTokenSilently])

  async function continueSignIn() {
    setRedirecting(true)

    try {
      await loginWithRedirect({
        authorizationParams: {
          redirect_uri: window.location.origin,
          audience: import.meta.env.VITE_AUTH0_AUDIENCE,
          ...(error?.code === 'consent_required'
            ? { prompt: 'consent' }
            : {}),
        },
      })
    } catch {
      setRedirecting(false)
      setError((previous) => ({
        ...previous,
        message: 'Could not open sign-in. Please try again.',
      }))
    }
  }

  if (error) {
    const needsInteraction =
      INTERACTIVE_ERRORS.includes(error.code)

    return (
      <main className="lp-app-status">
        <h1>
          {needsInteraction
            ? 'Complete your sign-in'
            : 'Could not load your account'}
        </h1>

        <p role="alert">
          {error.code === 'consent_required'
            ? 'Continue to Auth0 to review and approve access.'
            : error.message}
        </p>

        {needsInteraction && (
          <button
            type="button"
            onClick={continueSignIn}
            disabled={redirecting}
          >
            {redirecting
              ? 'Opening Auth0…'
              : 'Continue sign-in'}
          </button>
        )}
      </main>
    )
  }

  if (!ready) {
    return <p role="status">Loading your account…</p>
  }

  return children
}