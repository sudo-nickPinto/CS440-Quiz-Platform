import { useEffect, useState } from 'react'
import { useAuth0 } from '@auth0/auth0-react'
import { apiFetch, NEEDS_INTERACTION, returnToState } from '../api'
import AccountDisabledScreen from './AccountDisabledScreen'
import VerifyEmailScreen from './VerifyEmailScreen'

const REDIRECTED = 'quiz-interactive-login-tried'

// Loads the user's account from the backend, which creates it on first login,
// before showing the app. Everyone is a host/participant for now.
export default function AccountGate({ children }) {
  const { getAccessTokenSilently, loginWithRedirect, logout, user } = useAuth0()
  const [ready, setReady] = useState(false)
  const [error, setError] = useState('')
  const [unverified, setUnverified] = useState(false)
  const [disabled, setDisabled] = useState(false)

  useEffect(() => {
    let cancelled = false
    apiFetch('/me', getAccessTokenSilently)
      .then((account) => {
        if (cancelled) return
        try {
          sessionStorage.removeItem(REDIRECTED)
        } catch {
          // Storage may be unavailable.
        }
        // /me still answers for a deactivated account; every other route
        // would refuse it with inactive_account.
        if (account?.is_active === false) {
          setDisabled(true)
          return
        }
        setReady(true)
      })
      .catch((err) => {
        if (cancelled) return
        // The backend only links accounts with a verified email. Logging in
        // again won't help until the user clicks the link, so don't redirect.
        if (err.code === 'email_not_verified') {
          setUnverified(true)
          return
        }
        // A deactivated account stays deactivated however often it signs in.
        if (err.code === 'inactive_account') {
          setDisabled(true)
          return
        }
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
          // Re-authenticate as the same account rather than whichever account
          // the Auth0 session cookie belongs to.
          void loginWithRedirect({
            appState: returnToState(),
            authorizationParams: {
              prompt: 'login',
              ...(user?.email ? { login_hint: user.email } : {}),
            },
          }).catch(() => setError(err.message))
          return
        }
        setError(err.message)
      })
    return () => {
      cancelled = true
    }
  }, [getAccessTokenSilently, loginWithRedirect, user?.email])

  if (disabled) return <AccountDisabledScreen />

  if (unverified) {
    return (
      <VerifyEmailScreen
        onVerified={() => {
          setUnverified(false)
          setReady(true)
        }}
      />
    )
  }

  // Give a way out of an error instead of a dead-end message.
  if (error) {
    return (
      <div role="alert">
        <p className="error">{error}</p>
        <button
          type="button"
          onClick={() => logout({ logoutParams: { returnTo: window.location.origin } })}
        >
          Sign out and try again
        </button>
      </div>
    )
  }
  if (!ready) return <p className="muted" role="status">Loading…</p>
  return children
}
