import { useEffect, useRef, useState } from 'react'
import { useAuth0 } from '@auth0/auth0-react'
import { apiFetch, NEEDS_INTERACTION } from '../api'
import './VerifyEmailScreen.css'

// Shown when the backend refuses to create/link the account because the
// user's email isn't verified yet. onVerified runs once /me succeeds.
export default function VerifyEmailScreen({ onVerified }) {
  const { getAccessTokenSilently, loginWithRedirect, logout, user } = useAuth0()
  const headingRef = useRef(null)
  const [checking, setChecking] = useState(false)
  const [note, setNote] = useState('')

  // Move focus here so screen readers announce the new screen.
  useEffect(() => {
    headingRef.current?.focus()
  }, [])

  async function checkAgain() {
    if (checking) return
    setChecking(true)
    setNote('')
    try {
      // Auth0 only reflects the new email_verified state in a newly issued
      // token, and the backend reads it via /userinfo with that token, so
      // skip the token cache.
      await apiFetch('/me', () => getAccessTokenSilently({ cacheMode: 'off' }))
      onVerified()
      return
    } catch (err) {
      if (err.code === 'email_not_verified') {
        setNote('Still not verified. Check your spam folder.')
      } else if (NEEDS_INTERACTION.includes(err.error)) {
        // A fresh token needs an interactive login; stay on the same account.
        try {
          await loginWithRedirect({
            authorizationParams: {
              prompt: 'login',
              ...(user?.email ? { login_hint: user.email } : {}),
            },
          })
          return
        } catch {
          setNote('We could not open sign-in. Please log out and try again.')
        }
      } else {
        setNote(err.message || 'Something went wrong. Please try again.')
      }
    }
    setChecking(false)
  }

  return (
    <main className="verify-page">
      <section className="verify-card" aria-labelledby="verify-title">
        <div className="verify-card-top">
          <span>Almost there</span>
          <span>Verify email</span>
        </div>

        <div className="verify-card-body">
          <p className="verify-eyebrow">One more step</p>

          <h1 id="verify-title" ref={headingRef} tabIndex={-1}>
            Check your <span>inbox.</span>
          </h1>

          <p className="verify-text">
            We sent a verification link to{' '}
            {user?.email ? (
              <strong className="verify-email">{user.email}</strong>
            ) : (
              'your email address'
            )}
            . Click the link in that email, then come back here and continue.
          </p>

          <div className="verify-actions" aria-busy={checking}>
            <button
              className="verify-button verify-button-primary"
              type="button"
              disabled={checking}
              onClick={checkAgain}
            >
              <span>{checking ? 'Checking…' : "I've verified, continue"}</span>
              <span aria-hidden="true">→</span>
            </button>

            <button
              className="verify-button verify-button-secondary"
              type="button"
              onClick={() =>
                logout({ logoutParams: { returnTo: window.location.origin } })
              }
            >
              Log out
            </button>
          </div>

          <p className="verify-note" role="status">
            {note}
          </p>
        </div>
      </section>
    </main>
  )
}
