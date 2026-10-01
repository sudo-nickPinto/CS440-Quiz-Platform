import { useEffect, useState } from 'react'
import { useAuth0 } from '@auth0/auth0-react'
import { apiFetch } from '../api'

// Loads the user's account from the backend (creating it on first login).
// New users pick Student or Professor before seeing the app.
export default function AccountGate({ children }) {
  const { getAccessTokenSilently } = useAuth0()
  const [account, setAccount] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    apiFetch('/me', getAccessTokenSilently)
      .then(setAccount)
      .catch((err) => setError(err.message))
  }, [getAccessTokenSilently])

  const choose = (accountType) =>
    apiFetch('/me/account-type', getAccessTokenSilently, {
      method: 'POST',
      body: JSON.stringify({ account_type: accountType }),
    }).then(setAccount).catch((err) => setError(err.message))

  if (error) return <p className="error" role="alert">{error}</p>
  if (!account) return <p className="muted" role="status">Loading…</p>
  if (!account.account_type) {
    return <section aria-labelledby="type-title">
      <h1 id="type-title">Welcome! Are you a student or a professor?</h1>
      <button className="primary" type="button" onClick={() => choose('STUDENT')}>I'm a student</button>
      <button className="secondary" type="button" onClick={() => choose('PROFESSOR')}>I'm a professor</button>
    </section>
  }
  return children
}
