import { useState } from 'react'
import {
  Link,
  Navigate,
  NavLink,
  useNavigate,
  useParams,
} from 'react-router'

import { useAccount } from './account'
import { useAction, useApi, useResource } from './rest'
import RequestError from './RequestError'
import { ResumeSession } from './SessionPages'

export default function PreviewDashboard() {
  const { view } = useParams()
  const account = useAccount()
  const api = useApi()
  const navigate = useNavigate()

  const [query, setQuery] = useState('')
  const [sort, setSort] = useState('recent')

  const presenting = view === 'present'
  const resource = useResource(
    presenting ? '/quizzes' : null,
  )
  const action = useAction()

  if (!['present', 'participate'].includes(view)) {
    return (
      <Navigate to="/app/dashboard/present" replace />
    )
  }

  const quizzes = (resource.data || []).filter((quiz) =>
    quiz.author_id === account.account_id &&
    quiz.status === 'PUBLISHED' &&
    quiz.title.toLowerCase().includes(query.toLowerCase()),
  )

  if (sort === 'az') {
    quizzes.sort((a, b) => a.title.localeCompare(b.title))
  }

  async function host(quiz) {
    const session = await action.run(() =>
      api(`/quizzes/${quiz.quiz_id}/sessions`, {
        method: 'POST',
      }),
    )

    if (session) {
      navigate(`/app/host/${session.session_id}`)
    }
  }

  async function archive(quiz) {
    if (
      !window.confirm(
        `Archive "${quiz.title}"? It will no longer be hostable.`,
      )
    ) {
      return
    }

    const saved = await action.run(() =>
      api(`/quizzes/${quiz.quiz_id}/archive`, {
        method: 'PATCH',
      }),
    )

    if (saved) {
      resource.reload()
    }
  }

  return (
    <>
      <nav className="qp-tabs" aria-label="Dashboard">
        <NavLink to="/app/dashboard/present">
          Present
        </NavLink>
        <NavLink to="/app/dashboard/participate">
          Participate
        </NavLink>
        <Link to="/app/quizzes/new">＋ Create</Link>
        <Link to="/app/join">Join</Link>
      </nav>

      <section className="qp-content">
        <h1>
          {presenting ? 'Quizzes you made' : 'Participate'}
        </h1>

        <RequestError error={action.error} />

        {presenting ? (
          <>
            <div className="qp-toolbar">
              <label>
                Search
                <input
                  type="search"
                  value={query}
                  onChange={(event) =>
                    setQuery(event.target.value)
                  }
                />
              </label>

              <label>
                Sort
                <select
                  value={sort}
                  onChange={(event) =>
                    setSort(event.target.value)
                  }
                >
                  <option value="recent">
                    Newest first
                  </option>
                  <option value="az">A–Z</option>
                </select>
              </label>

              <button
                type="button"
                onClick={resource.reload}
                disabled={resource.loading || action.busy}
              >
                Refresh
              </button>
            </div>

            {resource.loading && (
              <p role="status">Loading quizzes…</p>
            )}

            <RequestError
              error={resource.error}
              retry={resource.reload}
            />

            {resource.data && !quizzes.length && (
              <p>
                No matching published quizzes.
                Create one to get started.
              </p>
            )}

            {quizzes.map((quiz) => (
              <article
                className="qp-row"
                key={quiz.quiz_id}
              >
                <span className="qp-badge">
                  {quiz.status}
                </span>

                <div>
                  <Link to={`/app/quizzes/${quiz.quiz_id}`}>
                    {quiz.title}
                  </Link>
                  <small>
                    {quiz.question_count} questions ·
                    Public · Read-only
                  </small>
                </div>

                <div className="qp-actions">
                  <button
                    type="button"
                    className="qp-primary"
                    disabled={action.busy}
                    onClick={() => void host(quiz)}
                  >
                    Host
                  </button>

                  <button
                    type="button"
                    disabled={action.busy}
                    onClick={() => void archive(quiz)}
                  >
                    Archive
                  </button>
                </div>
              </article>
            ))}
          </>
        ) : (
          <p>
            <Link
              className="qp-button"
              to="/app/join"
            >
              Join with a code
            </Link>
          </p>
        )}

        {action.busy && (
          <p role="status">Saving your request…</p>
        )}

        <h2>Return to a session</h2>
        <p>
          Session history is not connected yet. Keep your
          session URL, or enter its session ID below.
          This is different from the join code.
        </p>

        <ResumeSession
          mode={presenting ? 'host' : 'participant'}
        />
      </section>
    </>
  )
}
