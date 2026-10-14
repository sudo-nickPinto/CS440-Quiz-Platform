import { useCallback, useEffect, useState } from 'react'
import { useAuth0 } from '@auth0/auth0-react'
import { apiFetch } from '../api'
import './DashboardPage.css'
import './ApproveUsersPage.css'

// Loads the user's account from the backend, which creates it on first login,
// before showing the app. Email/password signups start PENDING and wait here
// until an Admin approves them on the Approve users page. `children` is a
// function that receives the loaded account.
export default function AccountGate({ children, onLogout }) {
  const { getAccessTokenSilently } = useAuth0()
  const [account, setAccount] = useState(null)
  const [error, setError] = useState('')
  const [checking, setChecking] = useState(false)

  const fetchAccount = useCallback(() => {
    apiFetch('/me', getAccessTokenSilently)
      .then((me) => {
        setAccount(me)
        setError('')
      })
      .catch((err) => setError(err.message))
      .finally(() => setChecking(false))
  }, [getAccessTokenSilently])

  useEffect(() => {
    fetchAccount()
  }, [fetchAccount])

  function check() {
    setChecking(true)
    fetchAccount()
  }

  if (account?.status === 'ACTIVE') return children(account)
  if (!account && !error) return <p className="muted" role="status">Loading…</p>

  return (
    <div className="dashboard-page">
      <main className="db-frame">
        <div className="au-pending">
          {error ? (
            <>
              <h1>Can’t sign you in</h1>
              <p role="alert">{error}</p>
            </>
          ) : account.status === 'DISABLED' ? (
            <>
              <h1>Account disabled</h1>
              <p>
                Your account ({account.email}) has been disabled. Ask an Admin
                if you think this is a mistake.
              </p>
            </>
          ) : (
            <>
              <h1>Waiting for approval</h1>
              <p>
                Your account ({account.email}) was created. An Admin needs to
                approve it before you can use the app. Ask your instructor,
                then check again.
              </p>
            </>
          )}

          <div className="au-pending-actions">
            <button
              type="button"
              className="db-primary"
              onClick={check}
              disabled={checking}
            >
              {checking ? 'Checking…' : 'Check again'}
            </button>
            <button type="button" className="db-control" onClick={onLogout}>
              Log out
            </button>
          </div>
        </div>
      </main>
    </div>
  )
}
