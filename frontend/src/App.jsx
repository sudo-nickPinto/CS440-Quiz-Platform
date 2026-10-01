import { useEffect, useRef } from 'react'
import { useAuth0 } from '@auth0/auth0-react'
import LoginPage from './components/LoginPage'
import LobbyPage from './components/LobbyPage'
import AccountGate from './components/AccountGate'
import './App.css'

// Non-secret markers (no tokens). WAS_SIGNED_IN lives across refreshes; TRIED
// lives only for this tab and stops us from redirecting in a loop.
const WAS_SIGNED_IN = 'quiz-was-signed-in'
const TRIED = 'quiz-silent-tried'
// Errors Auth0 sends back when there is simply no session to restore.
const NO_SESSION = ['login_required', 'consent_required', 'interaction_required']

export default function App() {
  // Login state now comes from Auth0 instead of a local mock user.
  const { isLoading, isAuthenticated, error, user: auth0User, loginWithRedirect, logout } = useAuth0()
  const heading = useRef(null)
  useEffect(() => { heading.current?.focus() }, [isAuthenticated, isLoading])

  // Outside dev, tokens are kept in memory only (see main.jsx), so a refresh
  // forgets them. If this browser
  // was signed in, ask Auth0 (prompt=none) whether its own session cookie is
  // still valid; if so we come straight back logged in.
  useEffect(() => {
    if (isLoading) return
    try {
      if (isAuthenticated) {
        localStorage.setItem(WAS_SIGNED_IN, '1')
        sessionStorage.removeItem(TRIED)
      } else if (error) {
        localStorage.removeItem(WAS_SIGNED_IN)
        sessionStorage.removeItem(TRIED)
      } else if (localStorage.getItem(WAS_SIGNED_IN) && !sessionStorage.getItem(TRIED)) {
        sessionStorage.setItem(TRIED, '1')
        loginWithRedirect({ authorizationParams: { prompt: 'none' } })
      }
    } catch { /* storage blocked: the user just logs in again */ }
  }, [isLoading, isAuthenticated, error, loginWithRedirect])

  // LobbyPage expects { name }, so build that from the Auth0 profile.
  const user = isAuthenticated ? { name: auth0User.name || auth0User.email } : null
  const logOut = () => {
    try { localStorage.removeItem(WAS_SIGNED_IN) } catch { /* ignore */ }
    logout({ logoutParams: { returnTo: window.location.origin } })
  }
  // "No session" isn't a real problem, so don't show it as an error.
  const realError = error && !NO_SESSION.includes(error.error) ? error : null

  let content
  if (isLoading) {
    content = <p className="muted" role="status">Loading…</p>
  } else if (realError) {
    content = <div>
      <p className="error" role="alert">Login problem: {realError.message}</p>
      <button className="primary" onClick={() => loginWithRedirect()}>Try again</button>
    </div>
  } else if (user) {
    content = <AccountGate>
      <LobbyPage user={user} headingRef={heading} />
    </AccountGate>
  } else {
    content = <LoginPage headingRef={heading} />
  }

  return <>
    <a className="skip-link" href="#main">Skip to content</a>
    <header className="site-header">
      <a className="brand" href="#main" aria-label="Classroom Quiz home">
        <span className="brand-mark" aria-hidden="true">Q</span>
        <span>Classroom<span className="brand-light">Quiz</span></span>
      </a>
      <div className="header-actions">
        {user && <button className="text-button" onClick={logOut}>Log out</button>}
      </div>
    </header>
    <main id="main">{content}</main>
    <footer>CS 440 · Gettysburg College <span>Made for a more connected classroom.</span></footer>
  </>
}
