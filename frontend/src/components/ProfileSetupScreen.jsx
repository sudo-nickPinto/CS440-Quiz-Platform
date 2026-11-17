import { useEffect, useRef } from 'react'
import { useAuth0 } from '@auth0/auth0-react'
import ProfileForm from './ProfileForm'
// Same sign-in card as the "Check your inbox" screen.
import './VerifyEmailScreen.css'

// Shown once, after email verification, until the account has a first and
// last name. Accounts made before profiles see it on their next sign-in.
export default function ProfileSetupScreen({ account, onSaved }) {
  const { logout } = useAuth0()
  const headingRef = useRef(null)

  // Move focus here so screen readers announce the new screen.
  useEffect(() => {
    headingRef.current?.focus()
  }, [])

  return (
    <main className="verify-page">
      <section className="verify-card" aria-labelledby="profile-title">
        <div className="verify-card-top">
          <span>Welcome to QuizBurg</span>
          <span>Your profile</span>
        </div>

        <div className="verify-card-body">
          <p className="verify-eyebrow">Last step</p>

          <h1 id="profile-title" ref={headingRef} tabIndex={-1}>
            Make it <span>yours.</span>
          </h1>

          <p className="verify-text">
            Add your name and pick an avatar. Hosts and other players see them
            in lobbies and on leaderboards.
          </p>

          <ProfileForm
            account={account}
            submitLabel="Save and continue"
            submitClassName="verify-button verify-button-primary"
            onSaved={onSaved}
          >
            <button
              className="verify-button verify-button-secondary"
              type="button"
              onClick={() =>
                logout({ logoutParams: { returnTo: window.location.origin } })
              }
            >
              Log out
            </button>
          </ProfileForm>
        </div>
      </section>
    </main>
  )
}
