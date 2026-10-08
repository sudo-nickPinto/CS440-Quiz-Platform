import { useEffect } from 'react'
import { useAuth0 } from '@auth0/auth0-react'
import { Navigate, Route, Routes } from 'react-router'
import LandingPage from './components/LandingPage'
import DashboardPage from './components/DashboardPage'
import AccountGate from './components/AccountGate'
import './App.css'

// Preserve the existing session-restoration markers.
const WAS_SIGNED_IN = 'quiz-was-signed-in'
const TRIED = 'quiz-silent-tried'

const NO_SESSION = [
  'login_required',
  'consent_required',
  'interaction_required',
]

export default function App() {
  const {
    isLoading,
    isAuthenticated,
    error,
    user: auth0User,
    loginWithRedirect,
    logout,
  } = useAuth0()

  useEffect(() => {
    if (isLoading) return

    try {
      if (isAuthenticated) {
        localStorage.setItem(WAS_SIGNED_IN, '1')
        sessionStorage.removeItem(TRIED)
        return
      }

      if (error) {
        localStorage.removeItem(WAS_SIGNED_IN)
        sessionStorage.removeItem(TRIED)
        return
      }

      const wasSignedIn = localStorage.getItem(WAS_SIGNED_IN)
      const alreadyTried = sessionStorage.getItem(TRIED)

      if (wasSignedIn && !alreadyTried) {
        sessionStorage.setItem(TRIED, '1')

        void loginWithRedirect({
          authorizationParams: {
            prompt: 'none',
          },
        }).catch(() => {
          // If redirect setup fails, leave the landing page available.
          // Keep TRIED for this tab to avoid an automatic retry loop.
          try {
            localStorage.removeItem(WAS_SIGNED_IN)
          } catch {
            // Storage may be unavailable.
          }
        })
      }
    } catch {
      // If browser storage is blocked, manual sign-in still works.
    }
  }, [
    isLoading,
    isAuthenticated,
    error,
    loginWithRedirect,
  ])

  function logOut() {
    try {
      localStorage.removeItem(WAS_SIGNED_IN)
      sessionStorage.removeItem(TRIED)
    } catch {
      // Logout can continue even when storage is blocked.
    }

    void logout({
      logoutParams: {
        returnTo: window.location.origin,
      },
    })
  }

  if (isLoading) {
    return (
      <main className="lp-app-status">
        <p role="status">Loading your session…</p>
      </main>
    )
  }

  if (isAuthenticated) {
    const userName =
      auth0User?.name ||
      auth0User?.email ||
      'User'

    return (
      <AccountGate>
        <Routes>
          <Route
            path="/dashboard/:view"
            element={
              <DashboardPage
                userName={userName}
                onLogout={logOut}
              />
            }
          />

          <Route
            path="*"
            element={
              <Navigate
                to="/dashboard/present"
                replace
              />
            }
          />
        </Routes>
      </AccountGate>
    )
  }

  const realError =
    error && !NO_SESSION.includes(error.error)
      ? 'Sign-in could not be completed. Please select Sign in and try again.'
      : ''

  return <LandingPage authError={realError} />
}