import { useEffect, useRef } from 'react'
import { useAuth0 } from '@auth0/auth0-react'
import './VerifyEmailScreen.css'

// Shown when the backend reports the account as deactivated
// (inactive_account). Signing in again won't help, so only offer sign-out.
export default function AccountDisabledScreen() {
  const { logout, user } = useAuth0()
  const headingRef = useRef(null)

  // Move focus here so screen readers announce the new screen.
  useEffect(() => {
    headingRef.current?.focus()
  }, [])

  return (
    <main className="verify-page">
      <section className="verify-card" aria-labelledby="disabled-title">
        <div className="verify-card-top">
          <span>Account</span>
          <span>Deactivated</span>
        </div>

        <div className="verify-card-body">
          <p className="verify-eyebrow">Access paused</p>

          <h1 id="disabled-title" ref={headingRef} tabIndex={-1}>
            This account is <span>deactivated.</span>
          </h1>

          <p className="verify-text">
            {user?.email ? (
              <strong className="verify-email">{user.email}</strong>
            ) : (
              'This account'
            )}{' '}
            can't use the quiz app right now. Contact an Admin if you think
            this is a mistake.
          </p>

          <div className="verify-actions">
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
        </div>
      </section>
    </main>
  )
}
