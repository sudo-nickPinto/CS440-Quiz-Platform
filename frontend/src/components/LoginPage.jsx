import { useAuth0 } from '@auth0/auth0-react'

export default function LoginPage({ headingRef }) {
  const { loginWithRedirect } = useAuth0()

  // Email + password: Auth0's hosted login page.
  const logIn = () => loginWithRedirect()
  // Same hosted page, opened on the sign-up screen.
  const signUp = () => loginWithRedirect({ authorizationParams: { screen_hint: 'signup' } })
  // Skips Auth0's page and goes straight to Google.
  const google = () => loginWithRedirect({ authorizationParams: { connection: 'google-oauth2' } })

  return <div className="login-layout">
    <section className="intro-panel" aria-labelledby="intro-title">
      <p className="eyebrow">GETTYSBURG COLLEGE · CS 440</p>
      <h2 id="intro-title">Classroom<span>Quiz!</span></h2>
      <p className="intro-copy">Big questions. Friendly competition.</p>
      <div className="answer-tiles" aria-hidden="true"><span>▲</span><span>◆</span><span>●</span><span>■</span></div>
    </section>
    <section className="login-form-panel" aria-labelledby="login-title">
      <h1 id="login-title" ref={headingRef} tabIndex={-1}>Ready to play?</h1>
      <p className="muted">Log in to join a quiz or host your own.</p>
      <button className="primary full-width" type="button" onClick={logIn}>Log in <span aria-hidden="true">→</span></button>
      <button className="secondary full-width" type="button" onClick={signUp}>Create account</button>
      <button className="secondary full-width" type="button" onClick={google}>Continue with Google</button>
    </section>
  </div>
}
