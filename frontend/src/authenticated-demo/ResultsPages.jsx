import { useState } from 'react'
import { Link, useParams } from 'react-router'
import { LETTERS, standings } from './model'
import { usePreview } from './store'

const outcome = (answer) =>
  answer.pick === null
    ? 'Missed'
    : answer.correct
      ? 'Correct'
      : 'Wrong'

function AnswerDetail({ question, answer, index }) {
  return (
    <article className="qp-card qp-content">
      <h2>Q{index + 1}. {question.text}</h2>

      <p>
        {outcome(answer)} · {answer.points} points
        {answer.seconds !== null &&
          ` · ${answer.seconds.toFixed(1)} seconds`}
      </p>

      <ol className="qp-review-options">
        {question.options.map((text, i) => (
          <li
            key={i}
            className={i === question.correct ? 'qp-correct' : ''}
          >
            <b>{LETTERS[i]}.</b> {text}

            {answer.pick === i && (
              <strong> · Selected answer</strong>
            )}

            {question.correct === i && (
              <strong> · Correct answer ✓</strong>
            )}
          </li>
        ))}
      </ol>

      {answer.pick === null && (
        <p>
          No answer was recorded before this question closed.
        </p>
      )}
    </article>
  )
}

export function ParticipantResults() {
  const { sessionId } = useParams()
  const { sessions } = usePreview()
  const [selected, setSelected] = useState(0)

  const session = sessions.find(
    (s) => s.id === sessionId && s.mode === 'participant',
  )

  if (!session || session.phase !== 'ended') {
    return (
      <p className="qp-content">
        Completed participant session not found.
      </p>
    )
  }

  const rows = standings(session)
  const me = rows.find((row) => row.id === 'me')

  const index = Math.min(
    selected,
    Math.max(0, me.answers.length - 1),
  )

  const answered = me.answers.filter(
    (a) => a.seconds !== null,
  )

  const average = answered.length
    ? (
        answered.reduce((sum, a) => sum + a.seconds, 0) /
        answered.length
      ).toFixed(1)
    : '—'

  return (
    <section className="qp-content">
      <Link to="/app/dashboard/participate">
        ← Participate
      </Link>

      <h1>{session.quiz.title}</h1>
      <p>
        Your results · {session.history.length} questions played
      </p>

      <div className="qp-stats">
        <div>
          <strong>{me.correct}/{session.history.length}</strong>
          Correct answers
        </div>

        <div>
          <strong>{me.points}</strong>
          Points
        </div>

        <div>
          <strong>#{me.rank}</strong>
          of {rows.length} participants
        </div>

        <div>
          <strong>{average}{answered.length ? 's' : ''}</strong>
          Average answer time
        </div>
      </div>

      {!me.answers.length ? (
        <p>This session ended before any questions were played.</p>
      ) : (
        <>
          <nav className="qp-tiles" aria-label="Your answers">
            {me.answers.map((answer, i) => (
              <button
                key={i}
                aria-pressed={index === i}
                onClick={() => setSelected(i)}
              >
                Q{i + 1}
                <small>
                  {outcome(answer)} · {answer.points} pts
                </small>
              </button>
            ))}
          </nav>

          <AnswerDetail
            question={session.quiz.questions[index]}
            answer={me.answers[index]}
            index={index}
          />

          <div className="qp-actions">
            <button
              disabled={index === 0}
              onClick={() => setSelected(index - 1)}
            >
              ← Previous
            </button>

            <button
              disabled={index === me.answers.length - 1}
              onClick={() => setSelected(index + 1)}
            >
              Next →
            </button>
          </div>
        </>
      )}
    </section>
  )
}

function downloadCsv(session, rows) {
  const quote = (value) => {
    let text = String(value ?? '')

    if (/^[\s]*[=+@-]/.test(text)) {
      text = "'" + text
    }

    return '"' + text.replaceAll('"', '""') + '"'
  }

  const scores = rows.map((row) => row.points)

  const data = [
    ['Quiz', session.quiz.title],
    ['Questions played', session.history.length],
    ['High score', Math.max(0, ...scores)],
    [
      'Average score',
      rows.length
        ? Math.round(
            scores.reduce((a, b) => a + b, 0) / rows.length,
          )
        : 0,
    ],
    ['Low score', scores.length ? Math.min(...scores) : 0],
    [],
    ['Rank', 'Participant', 'Correct', 'Points'],
    ...rows.map((row) => [
      row.rank,
      row.name,
      row.correct,
      row.points,
    ]),
    [],
    [
      'Participant',
      'Question',
      'Selected answer',
      'Correct answer',
      'Seconds',
      'Points',
    ],
    ...rows.flatMap((row) =>
      row.answers.map((answer, i) => {
        const q = session.quiz.questions[i]

        return [
          row.name,
          q.text,
          answer.pick === null
            ? 'No answer'
            : q.options[answer.pick],
          q.options[q.correct],
          answer.seconds,
          answer.points,
        ]
      }),
    ),
  ]

  const csv =
    '\uFEFF' +
    data.map((row) => row.map(quote).join(',')).join('\r\n')

  const url = URL.createObjectURL(
    new Blob([csv], { type: 'text/csv;charset=utf-8' }),
  )

  const link = document.createElement('a')
  link.href = url
  link.download = `quiz-results-${session.id}.csv`
  link.click()

  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export function HostResults() {
  const { sessionId } = useParams()
  const { sessions } = usePreview()
  const [tab, setTab] = useState('players')
  const [query, setQuery] = useState('')

  const session = sessions.find(
    (s) => s.id === sessionId && s.mode === 'host',
  )

  if (!session || session.phase !== 'ended') {
    return (
      <p className="qp-content">
        Completed host session not found.
      </p>
    )
  }

  const rows = standings(session)
  const questions = session.quiz.questions.slice(
    0,
    session.history.length,
  )

  const matches = (text) =>
    text.toLowerCase().includes(query.toLowerCase())

  const scores = rows.map((row) => row.points)

  return (
    <section className="qp-content">
      <div className="qp-actions">
        <Link to="/app/dashboard/present">← Present</Link>

        <button onClick={() => downloadCsv(session, rows)}>
          Export CSV for Excel
        </button>
      </div>

      <h1>{session.quiz.title}</h1>
      <p>Host results · {questions.length} questions played</p>

      <div className="qp-stats">
        <div>
          <strong>{rows.length}</strong>
          Participants
        </div>

        <div>
          <strong>{Math.max(0, ...scores)}</strong>
          High score
        </div>

        <div>
          <strong>
            {rows.length
              ? Math.round(
                  scores.reduce((a, b) => a + b, 0) / rows.length,
                )
              : 0}
          </strong>
          Average
        </div>

        <div>
          <strong>
            {scores.length ? Math.min(...scores) : 0}
          </strong>
          Low score
        </div>
      </div>

      <div className="qp-toolbar">
        <button
          aria-pressed={tab === 'players'}
          onClick={() => {
            setTab('players')
            setQuery('')
          }}
        >
          Leaderboard
        </button>

        <button
          aria-pressed={tab === 'questions'}
          onClick={() => {
            setTab('questions')
            setQuery('')
          }}
        >
          Questions
        </button>

        <label>
          Search {tab === 'players' ? 'participants' : 'questions'}
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
      </div>

      {tab === 'players' ? (
        <>
          {!rows.some((row) => matches(row.name)) && (
            <p>No matching participants.</p>
          )}

          {rows
            .filter((row) => matches(row.name))
            .map((row) => (
              <details className="qp-card qp-content" key={row.id}>
                <summary>
                  #{row.rank} · {row.name} · {row.points} pts ·{' '}
                  {row.correct}/{questions.length} correct
                </summary>

                {row.answers.map((answer, i) => (
                  <AnswerDetail
                    key={i}
                    question={questions[i]}
                    answer={answer}
                    index={i}
                  />
                ))}
              </details>
            ))}
        </>
      ) : (
        <>
          {!questions.some((q) => matches(q.text)) && (
            <p>No matching questions.</p>
          )}

          {questions.map(
            (q, i) =>
              matches(q.text) && (
                <details className="qp-card qp-content" key={q.id}>
                  <summary>Q{i + 1}. {q.text}</summary>

                  {q.options.map((text, pick) => {
                    const players = rows.filter(
                      (row) => row.answers[i].pick === pick,
                    )

                    return (
                      <div className="qp-distribution" key={pick}>
                        <span>
                          {LETTERS[pick]}. {text}
                          {pick === q.correct ? ' ✓ Correct' : ''}

                          <small>
                            {players.map((p) => p.name).join(', ') ||
                              'Nobody'}
                          </small>
                        </span>

                        <progress
                          max={rows.length || 1}
                          value={players.length}
                        />

                        <b>{players.length}</b>
                      </div>
                    )
                  })}

                  <p>
                    No answer:{' '}
                    {rows
                      .filter((row) => row.answers[i].pick === null)
                      .map((row) => row.name)
                      .join(', ') || 'Nobody'}
                  </p>
                </details>
              ),
          )}
        </>
      )}
    </section>
  )
}