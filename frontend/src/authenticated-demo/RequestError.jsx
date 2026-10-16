import { useAuth0 } from '@auth0/auth0-react'
import { NEEDS_INTERACTION } from '../api'

export default function RequestError({ error, retry }) {
  const { loginWithRedirect } = useAuth0()

  if (!error) return null

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

      {signInNeeded ? (
        <button
          type="button"
          onClick={() => {
            void loginWithRedirect().catch(() => {
              window.alert(
                'Sign-in could not start. Please reload and try again.',
              )
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
