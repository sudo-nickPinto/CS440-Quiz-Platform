import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { LETTERS, makeSession, standings } from './model'
import { dispatch, usePreview } from './store'

const SHAPES = ['▲', '◆', '●', '■', '★', '⬟']

export function JoinPage() {
  const state = usePreview()
  const navigate = useNavigate()
  const [code, setCode] = useState('')
  const [error, setError] = useState('')

  function join(e) {
    e.preventDefault()

    if (!/^\d{6}$/.test(code)) {
      setError('Enter exactly six digits.')
      return
    }

    if (code !== '482913') {
      setError('No demo session has that code. Use 482913.')
      return
    }

    const quiz = state.quizzes.find(
      (q) => q.id === 'data-structures',
    )

    const session = makeSession(
      crypto.randomUUID(),
      quiz,
      'participant',
      Date.now(),
    )

    dispatch({ type: 'CREATE_SESSION', session })
    navigate(`/app/play/${session.id}`)
  }

  return (
    <section className="qp-content qp-center">
      <Link to="/app/dashboard/participate">
        ← Dashboard
      </Link>

      <h1>Join a live quiz</h1>
      <p>Demo code: <strong>482913</strong></p>

      <form onSubmit={join}>
        <label>
          Session code
          <input
            className="qp-code"
            inputMode="numeric"
            autoComplete="off"
            maxLength={6}
            value={code}
            aria-invalid={Boolean(error)}
            aria-describedby={error ? 'join-error' : undefined}
            onChange={(e) => {
              setCode(
                e.target.value.replace(/\D/g, '').slice(0, 6),
              )
              setError('')
            }}
          />
        </label>

        {error && <p id="join-error" role="alert">{error}</p>}

        <button className="qp-primary">Join →</button>
      </form>
    </section>
  )
}

function useClock(session) {
  const [now, setNow] = useState(() => Date.now())
  const id = session?.id
  const phase = session?.phase
  const deadline = session?.deadline

  useEffect(() => {
    if (!['countdown', 'question'].includes(phase)) return

    const timer = setInterval(() => {
      const time = Date.now()
      setNow(time)

      if (time >= deadline) {
        dispatch({ type: 'TICK', id, now: time })
      }
    }, 100)

    return () => clearInterval(timer)
  }, [id, phase, deadline])

  return now
}

export function SessionPage({ mode }) {
  const { sessionId } = useParams()
  const { sessions } = usePreview()

  const session = sessions.find(
    (s) => s.id === sessionId && s.mode === mode,
  )

  const now = useClock(session)
  const [notice, setNotice] = useState('')

  if (!session) {
    return (
      <p className="qp-content">
        Session not found. Return to the dashboard.
      </p>
    )
  }

  const host = mode === 'host'
  const q = session.quiz.questions[session.index]
  const rows = standings(session)
  const me = rows.find((row) => row.id === 'me')
  const mine = session.history[session.index]?.me

  const seconds = Math.max(
    0,
    Math.ceil(((session.deadline || now) - now) / 1000),
  )

  const send = (type, extra = {}) =>
    dispatch({
      type,
      id: session.id,
      now: Date.now(),
      ...extra,
    })

  const resultPath =
    `/app/results/${host ? 'host' : 'me'}/${session.id}`

  return (
    <>
      <div className="qp-toolbar">
        <Link
          to={`/app/dashboard/${host ? 'present' : 'participate'}`}
        >
          ← Dashboard
        </Link>

        <strong>{session.quiz.title}</strong>
        <span>{host ? 'Host' : 'Participant'}</span>

        {session.phase !== 'ended' && (
          <button
            onClick={() => {
              if (
                window.confirm(
                  host
                    ? 'End this demo session?'
                    : 'Leave and finish this demo run?',
                )
              ) {
                send('END')
              }
            }}
          >
            {host ? 'End session' : 'Leave demo'}
          </button>
        )}
      </div>

      <div className="qp-content">
        {session.phase === 'lobby' && (
          <>
            <h1>{host ? 'Ready when you are.' : "You're in!"}</h1>
            <p>Session code</p>
            <div className="qp-code">{session.code}</div>

            <p>
              {session.quiz.questions.length} questions ·{' '}
              {session.players.length} simulated participants
            </p>

            <div className="qp-chips">
              {session.players.map((player) => (
                <span key={player.id}>{player.name}</span>
              ))}
            </div>

            <div className="qp-actions">
              {host && (
                <button
                  onClick={async () => {
                    try {
                      await navigator.clipboard.writeText(
                        session.code,
                      )
                      setNotice('Code copied.')
                    } catch {
                      setNotice(
                        `Copy this code manually: ${session.code}`,
                      )
                    }
                  }}
                >
                  Copy code
                </button>
              )}

              <button
                className="qp-primary"
                onClick={() => send('START')}
              >
                {host ? 'Start quiz' : 'Start simulated host'}
              </button>
            </div>

            {host && (
              <p className="qp-muted">
                The host code is illustrative; use 482913 for the
                separate participant demo.
              </p>
            )}
          </>
        )}

        {session.phase === 'countdown' && (
          <div className="qp-center">
            <h1>Get ready!</h1>
            <p>
              Question {session.index + 1} of{' '}
              {session.quiz.questions.length}
            </p>
            <strong className="qp-countdown" role="status">
              {Math.min(3, seconds)}
            </strong>
          </div>
        )}

        {session.phase === 'question' && (
          <>
            <div className="qp-bar">
              <span>
                Question {session.index + 1} of{' '}
                {session.quiz.questions.length}
              </span>

              <strong role="timer" aria-label="Seconds left">
                {Math.min(q.limit, seconds)}s
              </strong>
            </div>

            <progress
              aria-label="Time remaining"
              max={q.limit}
              value={Math.min(q.limit, seconds)}
            />

            {host ? (
              <>
                <h1>{q.text}</h1>

                <div className="qp-answer-grid">
                  {q.options.map((text, i) => (
                    <div
                      className={`qp-answer qp-answer-${i}`}
                      key={i}
                    >
                      <b>{SHAPES[i]} {LETTERS[i]}</b> {text}
                    </div>
                  ))}
                </div>

                <div className="qp-actions">
                  <button
                    className="qp-primary"
                    onClick={() => send('CLOSE')}
                  >
                    Close question
                  </button>

                  <button
                    onClick={async () => {
                      try {
                        if (document.fullscreenElement) {
                          await document.exitFullscreen()
                        } else {
                          await document.documentElement.requestFullscreen()
                        }
                      } catch {
                        setNotice(
                          'Fullscreen is unavailable in this browser.',
                        )
                      }
                    }}
                  >
                    Toggle fullscreen
                  </button>
                </div>
              </>
            ) : session.pick ? (
              <div className="qp-center" role="status">
                <h1>Answer submitted!</h1>
                <p>
                  You picked {LETTERS[session.pick.pick]}.
                  Wait for the question to close.
                </p>
              </div>
            ) : (
              <>
                <h1>Look at the classroom screen.</h1>

                <details className="qp-card qp-content">
                  <summary>Show simulated classroom screen</summary>
                  <h2>{q.text}</h2>
                  <ol type="A">
                    {q.options.map((text, i) => (
                      <li key={i}>{text}</li>
                    ))}
                  </ol>
                </details>

                <div className="qp-answer-grid">
                  {q.options.map((_, i) => (
                    <button
                      className={`qp-answer qp-answer-${i}`}
                      key={i}
                      aria-label={`Choose answer ${LETTERS[i]}`}
                      disabled={now >= session.deadline}
                      onClick={() => send('PICK', { pick: i })}
                    >
                      {SHAPES[i]} {LETTERS[i]}
                    </button>
                  ))}
                </div>
              </>
            )}

            {!host && (
              <button onClick={() => send('CLOSE')}>
                Demo: close question now
              </button>
            )}
          </>
        )}

        {session.phase === 'feedback' && (
          <>
            <h1>
              {host
                ? 'How did everyone answer?'
                : mine?.pick === null
                  ? "Time's up!"
                  : mine?.correct
                    ? 'Correct!'
                    : 'Not quite.'}
            </h1>

            <h2>{q.text}</h2>

            <p>
              Correct answer:{' '}
              <strong>
                {LETTERS[q.correct]} · {q.options[q.correct]}
              </strong>
            </p>

            {!host && (
              <p role="status">
                +{mine?.points || 0} points · Total{' '}
                {me?.points || 0} · Rank #{me?.rank}
              </p>
            )}

            {host &&
              q.options.map((text, i) => {
                const count = Object.values(
                  session.history[session.index],
                ).filter((a) => a.pick === i).length

                return (
                  <div className="qp-distribution" key={i}>
                    <span>
                      {LETTERS[i]}. {text}
                      {i === q.correct ? ' ✓' : ''}
                    </span>

                    <progress
                      max={session.players.length}
                      value={count}
                    />

                    <b>{count}</b>
                  </div>
                )
              })}

            <button
              className="qp-primary"
              onClick={() => send('BOARD')}
            >
              Leaderboard →
            </button>
          </>
        )}

        {session.phase === 'board' && (
          <>
            <h1>Leaderboard</h1>
            <Leaderboard rows={rows} />

            <button
              className="qp-primary"
              onClick={() => send('NEXT')}
            >
              {session.index + 1 === session.quiz.questions.length
                ? 'Final results'
                : host
                  ? 'Next question →'
                  : 'Demo host: next question →'}
            </button>
          </>
        )}

        {session.phase === 'ended' && (
          <>
            <h1>Final results</h1>

            <p>
              {session.history.length} of{' '}
              {session.quiz.questions.length} questions played
            </p>

            {session.history.length > 0 && (
              <>
                <div className="qp-podium">
                  {[rows[1], rows[0], rows[2]]
                    .filter(Boolean)
                    .map((row) => (
                      <div
                        className="qp-place"
                        data-rank={row.rank}
                        key={row.id}
                      >
                        <strong>#{row.rank}</strong>
                        <span>{row.name}</span>
                        <b>{row.points} points</b>
                      </div>
                    ))}
                </div>

                {!host && (
                  <p>
                    You got {me.correct}/{session.history.length}{' '}
                    correct.
                  </p>
                )}

                <Leaderboard rows={rows} />
              </>
            )}

            <Link
              className="qp-button qp-primary"
              to={resultPath}
            >
              Review results →
            </Link>
          </>
        )}

        <p role="status">{notice}</p>
      </div>
    </>
  )
}

function Leaderboard({ rows }) {
  return (
    <ol className="qp-leaderboard">
      {rows.map((row) => (
        <li key={row.id}>
          <strong>#{row.rank}</strong>
          <span>{row.name}</span>
          <b>{row.points} pts</b>
        </li>
      ))}
    </ol>
  )
}