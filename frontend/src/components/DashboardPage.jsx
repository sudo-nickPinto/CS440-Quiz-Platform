import { useEffect, useRef, useState } from 'react'
import { Link, Navigate, NavLink, useParams } from 'react-router'
import DashboardPopover from './DashboardPopover'
import {
  classes,
  madeQuizzes,
  takenQuizzes,
} from '../data/dashboardDemo'
import './DashboardPage.css'

export default function DashboardPage({
  userName = 'Preview User',
  onLogout,
  preview = false,
  made = madeQuizzes,
  taken = takenQuizzes,
  loading = false,
  error = '',
}) {
  const { view } = useParams()
  const base = preview ? '/preview/dashboard' : '/dashboard'

  if (view !== 'present' && view !== 'participate') {
    return <Navigate to={`${base}/present`} replace />
  }

  // Changing the view resets filters, menus, and form state.
  return (
    <DashboardView
      key={view}
      view={view}
      base={base}
      userName={userName}
      onLogout={onLogout}
      preview={preview}
      made={made}
      taken={taken}
      loading={loading}
      error={error}
    />
  )
}

function DashboardView({
  view,
  base,
  userName,
  onLogout,
  preview,
  made,
  taken,
  loading,
  error,
}) {
  const [query, setQuery] = useState('')
  const [owner, setOwner] = useState('all')
  const [sort, setSort] = useState('recent')
  const [joinOpen, setJoinOpen] = useState(false)
  const [code, setCode] = useState('')
  const [codeError, setCodeError] = useState('')
  const [notice, setNotice] = useState('')

  const heading = useRef(null)
  const joinButton = useRef(null)
  const noticeTimer = useRef(null)

  const presenting = view === 'present'
  const initials =
    userName.trim().split(/\s+/).slice(0, 2)
      .map((part) => part[0]).join('').toUpperCase() || '?'

  useEffect(() => {
    heading.current?.focus()

    return () => clearTimeout(noticeTimer.current)
  }, [])

  function notify(message) {
    clearTimeout(noticeTimer.current)
    setNotice(message)
    noticeTimer.current = setTimeout(() => setNotice(''), 4000)
  }

  function closeJoin() {
    setJoinOpen(false)
    setCodeError('')
    joinButton.current?.focus()
  }

  function submitJoin(event) {
    event.preventDefault()

    const normalized = code.trim().toUpperCase()

    // This matches the six-character mockup format.
    // The backend must ultimately define and validate session codes.
    if (!/^[A-Z0-9]{6}$/.test(normalized)) {
      setCodeError('Enter a six-character session code.')
      return
    }

    setCodeError('')
    notify(`Preview: joining ${normalized} will be connected to the lobby.`)
  }

  const search = query.trim().toLowerCase()

  const rows = (presenting ? made : taken)
    .filter((quiz) => quiz.title.toLowerCase().includes(search))
    .filter((quiz) => !presenting || owner === 'all' || quiz.owner === owner)
    .sort((a, b) => {
      if (sort === 'az') return a.title.localeCompare(b.title)

      if (sort === 'status') {
        return a.status.localeCompare(b.status)
      }

      if (sort === 'score') {
        return b.correct / b.total - a.correct / a.total
      }

      return (b.edited || b.date).localeCompare(a.edited || a.date)
    })

  const sortOptions = presenting
    ? [
        ['recent', 'Last edited'],
        ['az', 'A → Z'],
        ['status', 'Status'],
      ]
    : [
        ['recent', 'Most recent'],
        ['score', 'Best score'],
        ['az', 'A → Z'],
      ]

  return (
    <div className="dashboard-page">
      <a className="db-skip" href="#dashboard-content">
        Skip to quizzes
      </a>

      <header className="db-header">
        <Link className="db-logo" to={`${base}/present`}>
          QUIZ<span>.</span>PLATFORM
        </Link>

        <div className="db-user">
          <span className="db-name">{userName}</span>
          <span className="db-avatar" aria-hidden="true">
            {initials}
          </span>

          {preview ? (
            <Link className="db-control" to="/">Login page</Link>
          ) : (
            <button
              type="button"
              className="db-control"
              onClick={onLogout}
            >
              Log out
            </button>
          )}
        </div>
      </header>

      <p className="db-preview-note">
        Sample data · Quiz actions are previews
      </p>

      <main className="db-frame">
        <h1 ref={heading} tabIndex={-1} className="db-sr-only">
          {presenting ? 'Quizzes you made' : 'Quizzes you have taken'}
        </h1>

        <nav className="db-tabs" aria-label="Quiz dashboard">
          <NavLink
            className="db-tab db-present"
            to={`${base}/present`}
          >
            Present
          </NavLink>

          <NavLink
            className="db-tab db-participate"
            to={`${base}/participate`}
          >
            Participate
          </NavLink>

          <button
            type="button"
            className="db-plus"
            aria-label="Create a new quiz"
            onClick={() => notify('Preview: the quiz editor is not connected yet.')}
          >
            +
          </button>

          <button
            ref={joinButton}
            type="button"
            className="db-join"
            aria-expanded={joinOpen}
            aria-controls="dashboard-join"
            onClick={() => setJoinOpen((open) => !open)}
          >
            Join
          </button>
        </nav>

        {joinOpen && (
          <form
            id="dashboard-join"
            className="db-join-panel"
            onSubmit={submitJoin}
            onKeyDown={(event) => {
              if (event.key === 'Escape') closeJoin()
            }}
          >
            <label htmlFor="dashboard-code">Session code</label>

            <input
              id="dashboard-code"
              autoFocus
              autoComplete="off"
              maxLength={6}
              placeholder="ABC123"
              value={code}
              aria-invalid={Boolean(codeError)}
              aria-describedby={codeError ? 'dashboard-code-error' : undefined}
              onChange={(event) => {
                setCode(event.target.value.toUpperCase())
                setCodeError('')
              }}
            />

            <button className="db-primary" type="submit">Go →</button>

            <button
              className="db-control"
              type="button"
              onClick={closeJoin}
            >
              Cancel
            </button>

            {codeError && (
              <p id="dashboard-code-error" className="db-code-error" role="alert">
                {codeError}
              </p>
            )}
          </form>
        )}

        <div className="db-toolbar">
          <label className="db-search">
            <span className="db-sr-only">Search quizzes</span>
            <span aria-hidden="true">⌕</span>
            <input
              type="search"
              placeholder="Search quizzes…"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </label>

          <DashboardPopover
            label={owner !== 'all' || sort !== 'recent' ? 'Filter •' : 'Filter'}
            accessibleLabel="Filter and sort quizzes"
          >
            {() => (
              <>
                {presenting && (
                  <>
                    <p className="db-popover-label">Show</p>
                    <div className="db-options">
                      {['all', 'owned', 'shared'].map((value) => (
                        <button
                          key={value}
                          type="button"
                          aria-pressed={owner === value}
                          onClick={() => setOwner(value)}
                        >
                          {value}
                        </button>
                      ))}
                    </div>
                  </>
                )}

                <p className="db-popover-label">Sort by</p>

                <div className="db-options">
                  {sortOptions.map(([value, label]) => (
                    <button
                      key={value}
                      type="button"
                      aria-pressed={sort === value}
                      onClick={() => setSort(value)}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </>
            )}
          </DashboardPopover>

          <span className="db-count" role="status">
            <b>{rows.length}</b>
            <span>{presenting ? 'quizzes' : 'taken'}</span>
          </span>
        </div>

        <section
          id="dashboard-content"
          tabIndex={0}
          className={`db-list ${presenting ? 'db-made' : 'db-taken'}`}
          aria-label={presenting ? 'Made quizzes' : 'Taken quizzes'}
          aria-busy={loading}
        >
          {loading ? (
            <p className="db-empty" role="status">Loading quizzes…</p>
          ) : error ? (
            <p className="db-empty" role="alert">{error}</p>
          ) : rows.length === 0 ? (
            <p className="db-empty">
              {query || owner !== 'all'
                ? 'No quizzes match your search or filters.'
                : presenting
                  ? 'Nothing here yet. Use + to create a quiz.'
                  : 'Your completed quizzes will appear here.'}
            </p>
          ) : (
            <>
              <div className="db-head" aria-hidden="true">
                <span>{presenting ? 'Status' : 'Rank'}</span>
                <span>Quiz</span>
                <span className="db-mid">{presenting ? 'Class' : 'Score'}</span>
                <span className="db-wide">{presenting ? 'Owner' : 'Host'}</span>
                {presenting && <span className="db-wide">Qs</span>}
                <span className="db-wide">{presenting ? 'Edited' : 'Date'}</span>
                <span />
              </div>

              {rows.map((quiz) => (
                <article className="db-row" key={quiz.id}>
                  <div
                    className={`db-status ${
                      presenting ? `db-${quiz.status}` : 'db-rank'
                    }`}
                  >
                    {presenting ? quiz.status : (
                      <span>
                        <b>#{quiz.rank}</b>
                        <br />
                        of {quiz.participants}
                      </span>
                    )}
                  </div>

                  <div className="db-title">
                    <button
                      type="button"
                      onClick={() => notify(
                        `Preview: ${presenting ? 'editing' : 'reviewing'} “${quiz.title}” is not connected yet.`,
                      )}
                    >
                      {quiz.title}
                    </button>

                    <span className="db-meta">
                      {presenting
                        ? `${quiz.questions} questions · ${quiz.edited} · ${quiz.className || 'Not published'}${quiz.sharedBy ? ` · Shared by ${quiz.sharedBy}` : ''}`
                        : `${quiz.correct}/${quiz.total} correct · ${quiz.host} · ${quiz.date}`}
                    </span>
                  </div>

                  {presenting ? (
                    <>
                      <div className="db-cell db-mid">
                        {quiz.className || 'Not published'}
                      </div>
                      <div className="db-cell db-wide">
                        <span className="db-tag">
                          {quiz.owner === 'owned' ? 'Me' : `Shared · ${quiz.sharedBy}`}
                        </span>
                      </div>
                      <div className="db-cell db-wide">{quiz.questions}</div>
                      <div className="db-cell db-wide">{quiz.edited}</div>
                    </>
                  ) : (
                    <>
                      <div className="db-cell db-mid db-score">
                        {quiz.correct}/{quiz.total}
                      </div>
                      <div className="db-cell db-wide">{quiz.host}</div>
                      <div className="db-cell db-wide">{quiz.date}</div>
                    </>
                  )}

                  <div className="db-row-action">
                    {presenting ? (
                      <DashboardPopover
                        label="⋯"
                        accessibleLabel={`Actions for ${quiz.title}`}
                      >
                        {(close) => (
                          <>
                            {['Edit', 'Share'].map((action) => (
                              <button
                                key={action}
                                className="db-menu-item"
                                type="button"
                                onClick={() => {
                                  notify(`Preview: ${action.toLowerCase()} is not connected yet.`)
                                  close(true)
                                }}
                              >
                                {action}
                              </button>
                            ))}

                            <p className="db-popover-label">Publish to…</p>

                            {classes.map((className) => (
                              <button
                                className="db-menu-item"
                                key={className}
                                type="button"
                                onClick={() => {
                                  notify(`Preview: publishing to ${className} is not connected yet.`)
                                  close(true)
                                }}
                              >
                                {className}
                              </button>
                            ))}
                          </>
                        )}
                      </DashboardPopover>
                    ) : (
                      <button
                        className="db-control"
                        type="button"
                        aria-label={`Review ${quiz.title}`}
                        onClick={() => notify('Preview: the results page is not connected yet.')}
                      >
                        →
                      </button>
                    )}
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