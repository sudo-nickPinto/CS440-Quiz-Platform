import { useState } from 'react'
import { useAuth0 } from '@auth0/auth0-react'
import './LoginPage.css'

export default function LoginPage({ headingRef }) {
  const { loginWithRedirect } = useAuth0()
  const [pending, setPending] = useState('')
  const [error, setError] = useState('')

  async function startLogin(action) {
    if (pending) return

    setError('')
    setPending(action)

    const authorizationParams = {}

    if (action === 'signup') {
      authorizationParams.screen_hint = 'signup'
    }

    if (action === 'google') {
      authorizationParams.connection = 'google-oauth2'
    }

    try {
      await loginWithRedirect({
        authorizationParams,
        openUrl: (url) => window.location.replace(url),
      })
    } catch {
      setError('We could not open sign-in. Please try again.')
    } finally {
      setPending('')
    }
  }

  const busy = pending !== ''

  return (
    <div className="login-page">
      <div className="login-shell">
        <section
          className="login-intro"
          aria-labelledby="login-intro-title"
        >
          <p className="login-eyebrow">
            Gettysburg College · CS 440
          </p>

          <h2 id="login-intro-title">
            Classroom
            <br />
            <span className="login-highlight">Quiz.</span>
          </h2>

          <p className="login-lede">
            A shared space for classroom questions,
            participation, and learning.
          </p>

          <p className="login-detail">
            Join a live session or bring your class together
            with a quiz of your own.
          </p>

          <div className="login-tags" aria-label="Platform activities">
            <span>Participate</span>
            <span>Present</span>
            <span>Review</span>
          </div>
        </section>

        <section
          className="login-card"
          aria-labelledby="login-title"
        >
          <div className="login-card-top">
            <span>Your classroom starts here</span>
            <span>Sign in</span>
          </div>

          <div className="login-card-body">
            <p className="login-eyebrow">Welcome to your classroom</p>

            <h1
              id="login-title"
              ref={headingRef}
              tabIndex={-1}
            >
              Welcome <span>back.</span>
            </h1>

            <p className="login-description">
              Log in to join a quiz or host your own.
            </p>

            <div className="login-actions" aria-busy={busy}>
              <button
                className="login-button login-button-primary"
                type="button"
                disabled={busy}
                onClick={() => startLogin('login')}
              >
                <span>
                  {pending === 'login' ? 'Opening sign-in…' : 'Log in'}
                </span>
                <span aria-hidden="true">→</span>
              </button>

              <div className="login-divider">
                <span>or</span>
              </div>

              <button
                className="login-button login-button-secondary"
                type="button"
                disabled={busy}
                onClick={() => startLogin('google')}
              >
                {pending === 'google'
                  ? 'Opening Google…'
                  : 'Continue with Google'}
              </button>

              <p className="login-signup">
                New here?{' '}
                <button
                  className="login-text-button"
                  type="button"
                  disabled={busy}
                  onClick={() => startLogin('signup')}
                >
                  {pending === 'signup'
                    ? 'Opening registration…'
                    : 'Create an account'}
                </button>
              </p>
            </div>

            <p className="login-status" role="status">
              {busy ? 'Opening the secure sign-in page…' : ''}
            </p>

            {error && (
              <p className="login-error" role="alert">
                {error}
              </p>
            )}

            <p className="login-note">
              Sign in to access your quizzes and classroom activities.
            </p>
          </div>
        </section>
      </div>
    </div>
  )
}