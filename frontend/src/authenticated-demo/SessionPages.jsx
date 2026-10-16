import { useState } from 'react'
import {
  Link,
  Navigate,
  useNavigate,
  useParams,
} from 'react-router'

import { useAccount } from './account'
import { useAction, useApi, useResource } from './rest'
import RequestError from './RequestError'

export function ResumeSession({ mode }) {
  const [id, setId] = useState('')
  const navigate = useNavigate()

  return (
    <form
      className="qp-actions"
      onSubmit={(event) => {
        event.preventDefault()

        if (!/^[1-9][0-9]*$/.test(id.trim())) return

        navigate(
          `/app/${mode === 'host' ? 'host' : 'play'}/${id.trim()}`,
        )
      }}
    >
      <label>
        Session ID
        <input
          required
          inputMode="numeric"
          pattern="[1-9][0-9]*"
          value={id}
          onChange={(event) => setId(event.target.value)}
        />
      </label>

      <button type="submit">
        Open session
      </button>
    </form>
  )
}

export function JoinPage() {
  const [code, setCode] = useState('')
  const api = useApi()
  const action = useAction()
  const navigate = useNavigate()

  async function join(event) {
    event.preventDefault()

    const joined = await action.run(() =>
      api('/sessions/join', {
        method: 'POST',
        body: JSON.stringify({
          join_code: code.trim(),
        }),
      }),
    )

    if (joined) {
      navigate(`/app/play/${joined.session.session_id}`)
    }
  }

  return (
    <section className="qp-content">
      <Link to="/app/dashboard/participate">
        ← Dashboard
      </Link>

      <h1>Join a session</h1>

      <form onSubmit={join}>
        <fieldset
          disabled={action.busy}
          className="qp-form-fields"
        >
          <label>
            Six-digit join code
            <input
              required
              inputMode="numeric"
              pattern="[0-9]{6}"
              minLength={6}
              maxLength={6}
              value={code}
              onChange={(event) =>
                setCode(event.target.value)
              }
            />
          </label>

          <button
            className="qp-primary"
            type="submit"
          >
            {action.busy ? 'Joining…' : 'Join'}
          </button>
        </fieldset>
      </form>

      <RequestError error={action.error} />

      {action.error?.code === 'session_already_joined' && (
        <p>
          Open your previous session URL, or use the
          session ID below. The join endpoint does not
          return that ID for an already-joined account.
        </p>
      )}

      <h2>Already joined?</h2>
      <ResumeSession mode="participant" />
    </section>
  )
}

export function SessionPage({ mode }) {
  const { sessionId } = useParams()
  const account = useAccount()
  const validId = /^[1-9][0-9]*$/.test(sessionId)

  const session = useResource(
    validId ? `/sessions/${sessionId}` : null,
    3000,
  )

  const host =
    session.data?.host_id === account.account_id

  const roster = useResource(
    host
      ? `/sessions/${sessionId}/participants`
      : null,
    3000,
  )

  if (!validId) {
    return <p role="alert">Invalid session ID.</p>
  }

  if (session.loading) {
    return <p role="status">Loading session…</p>
  }

  if (session.error) {
    return (
      <RequestError
        error={session.error}
        retry={session.reload}
      />
    )
  }

  if (!session.data) return null

  if ((mode === 'host') !== host) {
    return (
      <Navigate
        to={`/app/${host ? 'host' : 'play'}/${sessionId}`}
        replace
      />
    )
  }

  return (
    <section className="qp-content">
      <Link
        to={`/app/dashboard/${host ? 'present' : 'participate'}`}
      >
        ← Dashboard
      </Link>

      <h1>{session.data.quiz_title}</h1>

      <p>
        Session ID:
        {' '}<strong>{session.data.session_id}</strong>
      </p>

      <p>
        Status:
        {' '}<strong>{session.data.status}</strong>
      </p>

      <p>Bookmark this URL to return to this session.</p>

      {host ? (
        <>
          <h2>
            Join code: {session.data.join_code}
          </h2>

          <h2>Participants</h2>

          {roster.loading && (
            <p role="status">
              Loading participants…
            </p>
          )}

          <RequestError
            error={roster.error}
            retry={roster.reload}
          />

          {roster.data && (
            <>
              <p>{roster.data.length} joined</p>

              {!roster.data.length && (
                <p>Waiting for participants.</p>
              )}

              <ul>
                {roster.data.map((person) => (
                  <li key={person.session_participant_id}>
                    {person.display_name}
                  </li>
                ))}
              </ul>
            </>
          )}
        </>
      ) : (
        <p>
          You joined as {account.display_name}.
        </p>
      )}

      <p className="qp-notice">
        This session is saved in the database.
        This integration stage supports joining and
        viewing the lobby. Live question controls,
        answering, and results will be connected
        in the next stage.
      </p>

      <p>
        Session details refresh every three seconds.
        Returning to the dashboard does not leave or
        end the session.
      </p>
    </section>
  )
}
