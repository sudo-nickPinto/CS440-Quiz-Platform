import { useState } from 'react'
import { useAuth0 } from '@auth0/auth0-react'
import { NEEDS_INTERACTION, returnToState } from '../api'

export default function RequestError({ error, retry }) {
  const { loginWithRedirect, logout } = useAuth0()
  const [signInFailed, setSignInFailed] = useState(false)

  if (!error) return null

  // The account was deactivated after the app loaded; retrying won't help.
  if (error.code === 'inactive_account') {
    return (
      <div className="qp-error" role="alert">
        <p>
          This account has been deactivated. Contact an Admin if you think
          this is a mistake.
        </p>
        <button
          type="button"
          onClick={() =>
            logout({ logoutParams: { returnTo: window.location.origin } })
          }
        >
          Log out
        </button>
      </div>
    )
  }

  const signInNeeded =
    error.status === 401 ||
    NEEDS_INTERACTION.includes(error.error)

  return (
    <div className="qp-error" role="alert">
      <p>{error.message || 'The request failed.'}</p>

      {error instanceof TypeError && (
        <p>
          Check your connection. If you were saving or hosting,
          the server may have completed the request; check before
          submitting again.
        </p>
      )}

      {signInFailed && (
        <p>Sign-in could not start. Please reload and try again.</p>
      )}

      {signInNeeded ? (
        <button
          type="button"
          onClick={() => {
            setSignInFailed(false)
            void loginWithRedirect({ appState: returnToState() }).catch(() => {
              setSignInFailed(true)
            })
          }}
        >
          Sign in again
        </button>
      ) : retry ? (
        <button type="button" onClick={retry}>
          Retry loading
        </button>
      ) : null}
    </div>
  )
}
