import { useCallback, useEffect, useRef, useState } from 'react'
import { useAuth0 } from '@auth0/auth0-react'
import { Link } from 'react-router'
import { apiFetch } from '../api'
import './DashboardPage.css'
import './ApproveUsersPage.css'

// Email/password signups start inactive; approving them here replaces
// Auth0's verification email. Open to every signed-in user while testing.
// Move it into the admin area (and require Admin on the backend) later.
export default function ApproveUsersPage({ userName = 'User', onLogout }) {
  const { getAccessTokenSilently } = useAuth0()
  const [pending, setPending] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busyId, setBusyId] = useState(null)
  const [notice, setNotice] = useState('')

  const noticeTimer = useRef(null)

  const initials =
    userName.trim().split(/\s+/).slice(0, 2)
      .map((part) => part[0]).join('').toUpperCase() || '?'

  const fetchPending = useCallback(() => {
    apiFetch('/accounts/pending', getAccessTokenSilently)
      .then((rows) => {
        setPending(rows)
        setError('')
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [getAccessTokenSilently])

  useEffect(() => {
    fetchPending()

    return () => clearTimeout(noticeTimer.current)
  }, [fetchPending])

  function refresh() {
    setLoading(true)
    fetchPending()
  }

  function notify(message) {
    clearTimeout(noticeTimer.current)
    setNotice(message)
    noticeTimer.current = setTimeout(() => setNotice(''), 4000)
  }

  async function decide(person, approve) {
    setBusyId(person.account_id)
    try {
      await apiFetch(
        approve
          ? `/accounts/${person.account_id}/approve`
          : `/accounts/${person.account_id}`,
        getAccessTokenSilently,
        { method: approve ? 'POST' : 'DELETE' },
      )
      setPending((rows) => rows.filter((row) => row.account_id !== person.account_id))
      notify(`${approve ? 'Approved' : 'Rejected'} ${person.display_name}.`)
    } catch (err) {
      notify(err.message)
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="dashboard-page">
      <header className="db-header">
        <Link className="db-logo" to="/dashboard/present">
          QUIZ<span>.</span>PLATFORM
        </Link>

        <div className="db-user">
          <span className="db-name">{userName}</span>
          <span className="db-avatar" aria-hidden="true">
            {initials}
          </span>
          <button type="button" className="db-control" onClick={onLogout}>
            Log out
          </button>
        </div>
      </header>

      <p className="db-preview-note">
        Testing: every signed-in user can approve accounts for now
      </p>

      <main className="db-frame">
        <div className="au-titlebar">
          <h1>Approve users</h1>
          <Link className="au-back" to="/dashboard/present">
            ← Dashboard
          </Link>
        </div>

        <div className="db-toolbar">
          <p className="au-help">
            New accounts wait here until someone approves them.
          </p>

          <button
            type="button"
            className="db-control"
            onClick={refresh}
            disabled={loading}
          >
            Refresh
          </button>

          <span className="db-count" role="status">
            <b>{pending.length}</b>
            <span>pending</span>
          </span>
        </div>

        <section
          className="db-list au-list"
          aria-label="Accounts waiting for approval"
          aria-busy={loading}
        >
          {loading ? (
            <p className="db-empty" role="status">Loading accounts…</p>
          ) : error ? (
            <p className="db-empty" role="alert">{error}</p>
          ) : pending.length === 0 ? (
            <p className="db-empty">Nobody is waiting for approval.</p>
          ) : (
            <>
              <div className="db-head" aria-hidden="true">
                <span>Status</span>
                <span>Person</span>
                <span className="db-wide">Signed up</span>
                <span />
              </div>

              {pending.map((person) => (
                <article className="db-row" key={person.account_id}>
                  <div className="db-status db-draft">Pending</div>

                  <div className="db-title">
                    <span className="au-name">{person.display_name}</span>
                    <span className="au-email">{person.email}</span>
                  </div>

                  <div className="db-cell db-wide">
                    {new Date(person.created_at).toLocaleString()}
                  </div>

                  <div className="au-actions">
                    <button
                      type="button"
                      className="db-primary"
                      disabled={busyId === person.account_id}
                      aria-label={`Approve ${person.display_name}`}
                      onClick={() => decide(person, true)}
                    >
                      Approve
                    </button>
                    <button
                      type="button"
                      className="db-control"
                      disabled={busyId === person.account_id}
                      aria-label={`Reject ${person.display_name}`}
                      onClick={() => decide(person, false)}
                    >
                      Reject
                    </button>
                  </div>
                </article>
              ))}
            </>
          )}
        </section>
      </main>

      <div
        className={`db-toast ${notice ? 'db-toast-visible' : ''}`}
        role="status"
        aria-live="polite"
      >
        {notice}
      </div>
    </div>
  )
}
