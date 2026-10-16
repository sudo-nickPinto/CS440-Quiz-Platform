import { useState } from 'react'
import {
  Link,
  Navigate,
  NavLink,
  useNavigate,
  useParams,
} from 'react-router'
import { makeSession, standings } from './model'
import { dispatch, usePreview } from './store'

export default function PreviewDashboard() {
  const { view } = useParams()
  const navigate = useNavigate()
  const state = usePreview()

  const [query, setQuery] = useState('')
  const [sort, setSort] = useState('recent')

  if (!['present', 'participate'].includes(view)) {
    return <Navigate to="/app/dashboard/present" replace />
  }

  const presenting = view === 'present'
  const matches = (title) =>
    title.toLowerCase().includes(query.toLowerCase())

  const quizzes = state.quizzes.filter((q) => matches(q.title))

  if (sort === 'az') {
    quizzes.sort((a, b) => a.title.localeCompare(b.title))
  }

  const sessions = state.sessions.filter(
    (s) =>
      s.mode === (presenting ? 'host' : 'participant') &&
      matches(s.quiz.title),
  )

  return (
    <>
      <nav className="qp-tabs" aria-label="Dashboard">
        <NavLink to="/app/dashboard/present">
          Present
        </NavLink>

        <NavLink to="/app/dashboard/participate">
          Participate
        </NavLink>

        <Link to="/app/quizzes/new" aria-label="Create quiz">
          ＋ Create
        </Link>

        <Link to="/app/join">Join</Link>
      </nav>

      <div className="qp-toolbar">
        <label>
          Search
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>

        {presenting && (
          <label>
            Sort
            <select
              value={sort}
              onChange={(e) => setSort(e.target.value)}
            >
              <option value="recent">Newest first</option>
              <option value="az">A–Z</option>
            </select>
          </label>
        )}

        <span>One shared class</span>
      </div>

      <section className="qp-content">
        <h1>
          {presenting ? 'Quizzes you made' : 'Your sessions'}
        </h1>

        {presenting && (
          <>
            {!quizzes.length && (
              <p>No matching quizzes. Create one to get started.</p>
            )}

            {quizzes.map((quiz) => (
              <article className="qp-row" key={quiz.id}>
                <span className="qp-badge">{quiz.status}</span>

                <div>
                  <Link to={`/app/quizzes/${quiz.id}`}>
                    {quiz.title}
                  </Link>
                  <small>
                    {quiz.questions.length} questions · Public · Read-only
                  </small>
                </div>

                {quiz.status !== 'archived' && (
                  <div className="qp-actions">
                    <button
                      className="qp-primary"
                      onClick={() => {
                        const session = makeSession(
                          crypto.randomUUID(),
                          quiz,
                          'host',
                          Date.now(),
                        )

                        dispatch({
                          type: 'CREATE_SESSION',
                          session,
                        })

                        navigate(`/app/host/${session.id}`)
                      }}
                    >
                      Host
                    </button>

                    <button
                      onClick={() => {
                        if (
                          window.confirm(
                            `Archive "${quiz.title}" in this preview?`,
                          )
                        ) {
                          dispatch({
                            type: 'ARCHIVE',
                            id: quiz.id,
                          })
                        }
                      }}
                    >
                      Archive
                    </button>
                  </div>
                )}
              </article>
            ))}

            <h2>Hosted sessions</h2>
          </>
        )}

        {!sessions.length && <p>No matching sessions yet.</p>}

        {sessions.map((session) => {
          const me = standings(session).find(
            (row) => row.id === 'me',
          )

          const resultPath = presenting ? 'host' : 'me'
          const livePath = presenting ? 'host' : 'play'

          return (
            <article className="qp-row" key={session.id}>
              <span className="qp-badge">
                {session.phase === 'ended'
                  ? 'Finished'
                  : 'In progress'}
              </span>

              <div>
                <strong>{session.quiz.title}</strong>
                <small>
                  {new Date(session.createdAt).toLocaleDateString()}
                  {me &&
                    ` · ${me.correct}/${session.history.length} correct · ${me.points} points`}
                </small>
              </div>

              <Link
                className="qp-button"
                to={
                  session.phase === 'ended'
                    ? `/app/results/${resultPath}/${session.id}`
                    : `/app/${livePath}/${session.id}`
                }
              >
                {session.phase === 'ended'
                  ? 'View results'
                  : 'Resume'}
              </Link>
            </article>
          )
        })}
      </section>
    </>
  )
}