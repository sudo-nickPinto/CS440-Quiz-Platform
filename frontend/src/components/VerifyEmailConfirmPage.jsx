import { useEffect, useMemo, useState } from 'react'
import { Link, useLocation } from 'react-router'
import { verificationTarget } from '../verifyEmailLink'
import './VerifyEmailScreen.css'
import './VerifyEmailConfirmPage.css'

// /verify-email: where the verification email sends people. Auth0 verifies
// an address as soon as its link is loaded, and school mail scanners load
// every link in a message, so the email links here instead and only a click
// on "Confirm my email" opens Auth0's link (carried in the URL fragment).
// Shown the same way whether or not anyone is signed in.
export default function VerifyEmailConfirmPage() {
  const { hash } = useLocation()
  const target = useMemo(
    () => verificationTarget(hash, import.meta.env.VITE_AUTH0_DOMAIN),
    [hash],
  )
  const [opening, setOpening] = useState(false)

  // Coming back with the Back button can restore this page from the cache
  // with the button still disabled; make it usable again.
  useEffect(() => {
    function onPageShow(event) {
      if (event.persisted) setOpening(false)
    }
    window.addEventListener('pageshow', onPageShow)
    return () => window.removeEventListener('pageshow', onPageShow)
  }, [])

  function confirm() {
    if (!target || opening) return
    setOpening(true)
    window.location.assign(target)
  }

  if (!target) {
    return (
      <main className="verify-page">
        <section className="verify-card" aria-labelledby="verify-link-title">
          <div className="verify-card-top">
            <span>QuizBurg</span>
            <span>Verify email</span>
          </div>

          <div className="verify-card-body">
            <p className="verify-eyebrow">Verification link</p>

            <h1 id="verify-link-title">
              This link <span>doesn't work</span>
            </h1>

            <p className="verify-text">
              Open the newest verification email from QuizBurg and use the
              button in it. Check your spam folder too. Already verified? Sign
              in and select “I've verified, continue”.
            </p>

            <div className="verify-actions">
              <Link
                className="verify-button verify-button-secondary"
                to="/"
              >
                Go to the QuizBurg home page
              </Link>
            </div>
          </div>
        </section>
      </main>
    )
  }

  return (
    <main className="verify-page">
      <section className="verify-card" aria-labelledby="verify-confirm-title">
        <div className="verify-card-top">
          <span>Almost there</span>
          <span>Verify email</span>
        </div>

        <div className="verify-card-body">
          <p className="verify-eyebrow">One last step</p>

          <h1 id="verify-confirm-title">
            Confirm your <span>email</span>
          </h1>

          <p className="verify-text">
            Press the button to finish verifying your QuizBurg account.
          </p>

          <div className="verify-actions" aria-busy={opening}>
            <button
              className="verify-button verify-button-primary"
              type="button"
              disabled={opening}
              onClick={confirm}
            >
              <span>{opening ? 'Opening…' : 'Confirm my email'}</span>
              <span aria-hidden="true">→</span>
            </button>
          </div>
        </div>
      </section>
    </main>
  )
}
