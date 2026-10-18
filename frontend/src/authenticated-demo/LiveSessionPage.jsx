import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import { useLiveSession } from '../live/useLiveSession'
import { useAction } from './rest'
import RequestError from './RequestError'
import './live-session.css'

const LETTERS = ['A', 'B', 'C', 'D']

const CONNECTION_ERRORS = {
  unauthorized: 'Your login needs to be renewed.',
  forbidden: 'You cannot access this live session.',
  not_found: 'This session does not exist.',
  replaced: 'This session was opened elsewhere using the same account.',
  failed: 'The live connection failed because of a protocol error.',
  closed: 'The live connection is closed.',
}

function reloadPage() {
  window.location.reload()
}

function Countdown({ closesAt }) {
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    const timer = window.setInterval(() => {
      setNow(Date.now())
    }, 250)

    return () => window.clearInterval(timer)
  }, [])

  const deadline = Date.parse(closesAt)
  const remaining = Number.isFinite(deadline)
    ? Math.max(0, Math.ceil((deadline - now) / 1000))
    : null

  return (
    <p className="live-timer">
      {remaining === null
        ? 'Timer unavailable'
        : remaining > 0
          ? `${remaining}s remaining`
          : 'Waiting for the server to close the question…'}
    </p>
  )
}

function Standings({ rows, final = false }) {
  if (!rows.length) {
    return <p>No standings available.</p>
  }

  return (
    <div className="live-table-wrap">
      <table className="live-table">
        <caption>
          {final ? 'Final standings' : 'Current standings'}
        </caption>
        <thead>
          <tr>
            <th scope="col">Rank</th>
            <th scope="col">Participant</th>
            <th scope="col">Points</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={row.session_participant_id ?? index}>
              <td>{final ? row.final_rank : row.rank}</td>
              <td>{row.display_name}</td>
              <td>
                {final ? row.total_score : row.cumulative_score}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function QuestionResults({ question, results, host }) {
  if (!question) return null

  const me = results?.me
  const correctIds = results?.correct_choice_ids || []

  return (
    <section className="live-panel" aria-labelledby="question-results">
      <h2 id="question-results">
        Question {question.question_order} results
      </h2>

      <p>{question.question_text}</p>

      {!results ? (
        <p role="status">Loading the server’s results…</p>
      ) : (
        <>
          <ul className="live-choice-review">
            {question.choices.map((choice, index) => {
              const correct = correctIds.includes(choice.choice_id)
              const selected = me?.selected_choice_id === choice.choice_id
              const count = results.choices?.find(
                (item) => item.choice_id === choice.choice_id,
              )?.response_count

              return (
                <li key={choice.choice_id}>
                  <strong>
                    {LETTERS[index]}. {choice.choice_text}
                  </strong>
                  {correct && <span> — Correct answer</span>}
                  {selected && <span> — Your answer</span>}
                  {count !== undefined && (
                    <span> — {count} responses</span>
                  )}
                </li>
              )
            })}
          </ul>

          {!host && (
            me ? (
              <p>
                {me.selected_choice_id == null
                  ? 'No answer recorded.'
                  : me.is_correct
                    ? 'Your answer was correct.'
                    : 'Your answer was incorrect.'}
                {' '}Points earned: {me.points_awarded}.
                {' '}Total: {me.cumulative_score}.
                {' '}Rank: {me.rank}.
              </p>
            ) : (
              <p>You do not have a result for this question.</p>
            )
          )}

          <Standings
            rows={
              host
                ? results.participants || []
                : results.leaderboard || []
            }
          />
        </>
      )}
    </section>
  )
}

function FinalResults({ results, error }) {
  if (!results) {
    return (
      <section className="live-panel">
        <h2>Session ended</h2>
        {error ? (
          <RequestError error={error} retry={reloadPage} />
        ) : (
          <p role="status">Loading saved results…</p>
        )}
      </section>
    )
  }

  const cancelled =
    results.status === 'CANCELLED' ||
    results.reason === 'CANCELLED'

  const hostView = Array.isArray(results.standings)
  const rows = hostView
    ? results.standings
    : results.leaderboard || []

  return (
    <section className="live-panel">
      <h2>{cancelled ? 'Session cancelled' : 'Final results'}</h2>

      {cancelled ? (
        <p>The host cancelled this session before play began.</p>
      ) : (
        <>
          {!hostView && results.me && (
            <p>
              Your score: <strong>{results.me.total_score}</strong>
              {' '}· Correct answers: {results.me.correct_count}
              {' '}· Rank: {results.me.final_rank}
            </p>
          )}

          {!hostView && !results.me && (
            <p>No individual result is available for your account.</p>
          )}

          <Standings rows={rows} final />

          <p>
            These results are saved on the server.
            Bookmark this session URL to return later.
          </p>
        </>
      )}
    </section>
  )
}

function ConnectedSession({ sessionId }) {
  const live = useLiveSession(sessionId)
  const action = useAction()

  const { state, phase } = live
  const host = state.role === 'host'
  const connected = state.connection === 'open'
  const question = state.currentQuestion
  const terminalMessage = CONNECTION_ERRORS[state.connection]

  const canAct = connected && !action.busy
  const canAdvance =
    canAct &&
    host &&
    live.nextQuestionOrder !== null &&
    state.participantCount > 0 &&
    (
      phase === 'lobby' ||
      phase === 'waiting' ||
      (phase === 'results' && Boolean(state.lastResults))
    )

  const dashboard =
    host || Array.isArray(state.final?.standings)
      ? '/app/dashboard/present'
      : '/app/dashboard/participate'

  function run(command) {
    void action.run(command)
  }

  function confirmAndRun(message, command) {
    if (window.confirm(message)) {
      run(command)
    }
  }

  const connectionError = terminalMessage
    ? {
        message: terminalMessage,
        status: state.connection === 'unauthorized' ? 401 : undefined,
      }
    : null

  return (
    <section className="qp-content live-session">
      <Link to={dashboard}>← Dashboard</Link>

      <h1>Live session {sessionId}</h1>

      <p role="status">
        Connection: <strong>{state.connection}</strong>
      </p>

      <RequestError
        error={connectionError}
        retry={
          ['replaced', 'failed', 'closed'].includes(state.connection)
            ? reloadPage
            : undefined
        }
      />

      {!terminalMessage && (
        <>
          {state.connection === 'reconnecting' && (
            <p className="qp-notice" role="status">
              Reconnecting. Controls are paused until a new server
              snapshot arrives. Displayed information may be outdated.
            </p>
          )}

          {phase === 'connecting' && (
            <p role="status">Connecting to the live session…</p>
          )}

          {phase === 'left' && (
            <section className="live-panel">
              <h2>You left the session</h2>
              <p>Return to the dashboard to continue.</p>
            </section>
          )}

          {phase === 'ended' && (
            <FinalResults
              results={state.final}
              error={state.lastError}
            />
          )}

          {state.session && !['ended', 'left'].includes(phase) && (
            <>
              <p>
                {host ? 'Hosting' : 'Participating'}
                {' '}· {state.participantCount} participants
                {' '}· {state.session.total_questions} questions
              </p>

              {!host && !state.hostConnected && (
                <p className="qp-notice" role="status">
                  The host is disconnected. Open questions still follow
                  the server timer while we wait for the host to return.
                </p>
              )}

              {phase === 'lobby' && (
                <section className="live-panel">
                  <h2>{host ? 'Host lobby' : 'Waiting for the host'}</h2>

                  {host ? (
                    <>
                      <p className="live-code">
                        Join code: <strong>{state.session.join_code}</strong>
                      </p>

                      <h3>Participants</h3>

                      {state.participants.length > 0 ? (
                        <ul>
                          {state.participants.map((person) => (
                            <li key={person.session_participant_id}>
                              {person.display_name}
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p>
                          {state.participantCount > 0
                            ? 'Participant names are not available yet.'
                            : 'Waiting for participants to join.'}
                        </p>
                      )}
                    </>
                  ) : (
                    <p>
                      You have joined. The first question will appear
                      when the host starts the quiz.
                    </p>
                  )}
                </section>
              )}

              {phase === 'question' && question && (
                <section className="live-panel">
                  <h2>
                    Question {question.question_order}
                    {' '}of {question.total_questions}
                  </h2>

                  <Countdown
                    key={question.session_question_id}
                    closesAt={question.closes_at}
                  />

                  {host ? (
                    <>
                      <h3>{question.question_text}</h3>

                      <div className="live-answers">
                        {question.choices.map((choice, index) => (
                          <div
                            className={`live-choice live-choice-${index}`}
                            key={choice.choice_id}
                          >
                            <strong>{LETTERS[index]}.</strong>
                            {' '}{choice.choice_text}
                          </div>
                        ))}
                      </div>

                      <p role="status">
                        {state.answerProgress
                          ? `${state.answerProgress.answered_count} of ${
                              state.answerProgress.eligible_count
                            } eligible participants answered.`
                          : 'Waiting for the next answer-progress update.'}
                      </p>
                    </>
                  ) : (
                    <>
                      <p>
                        Read the question on the host’s screen, then
                        choose the matching answer.
                      </p>

                      <div className="live-answers">
                        {question.choices.map((choice, index) => (
                          <button
                            type="button"
                            className={`live-choice live-choice-${index}`}
                            key={choice.choice_id}
                            disabled={!canAct || Boolean(state.myAnswer)}
                            aria-label={`Answer ${LETTERS[index]}`}
                            aria-pressed={
                              state.myAnswer?.choice_id === choice.choice_id
                            }
                            onClick={() => {
                              run(() => live.submitAnswer(choice.choice_id))
                            }}
                          >
                            Answer {LETTERS[index]}
                          </button>
                        ))}
                      </div>

                      {state.myAnswer && (
                        <p role="status">
                          Your answer was recorded. Waiting for the
                          question to close.
                        </p>
                      )}
                    </>
                  )}
                </section>
              )}

              {phase === 'results' && (
                <QuestionResults
                  question={state.lastQuestion}
                  results={state.lastResults}
                  host={host}
                />
              )}

              {phase === 'waiting' && (
                <p role="status">
                  Waiting for the next question.
                </p>
              )}

              {host ? (
                <div className="live-controls">
                  {['lobby', 'results', 'waiting'].includes(phase) &&
                    live.nextQuestionOrder !== null && (
                      <button
                        type="button"
                        className="qp-primary"
                        disabled={!canAdvance}
                        onClick={() => run(live.openNextQuestion)}
                      >
                        {phase === 'lobby'
                          ? 'Start quiz'
                          : 'Next question'}
                      </button>
                    )}

                  {phase === 'question' && (
                    <button
                      type="button"
                      disabled={!canAct}
                      onClick={() => run(live.skip)}
                    >
                      Close question now
                    </button>
                  )}

                  {state.session.status === 'LOBBY' && (
                    <button
                      type="button"
                      disabled={!canAct}
                      onClick={() => {
                        confirmAndRun(
                          'Cancel this lobby for everyone?',
                          live.cancel,
                        )
                      }}
                    >
                      Cancel session
                    </button>
                  )}

                  {state.session.status === 'ACTIVE' && (
                    <button
                      type="button"
                      disabled={!canAct}
                      onClick={() => {
                        confirmAndRun(
                          'End the session and save the final results?',
                          live.end,
                        )
                      }}
                    >
                      End session
                    </button>
                  )}

                  {phase === 'results' &&
                    live.nextQuestionOrder === null && (
                      <p>
                        All questions are complete. Select End session
                        to save the final results.
                      </p>
                    )}
                </div>
              ) : (
                <div className="live-controls">
                  <button
                    type="button"
                    disabled={!canAct}
                    onClick={() => {
                      confirmAndRun(
                        'Leave this session?',
                        live.leave,
                      )
                    }}
                  >
                    Leave session
                  </button>
                </div>
              )}

              {action.busy && (
                <p role="status">Waiting for server confirmation…</p>
              )}

              <RequestError error={action.error} />

              <p className="live-help">
                Returning to the dashboard disconnects this page.
                Use the session controls to explicitly leave, cancel,
                or end the session.
              </p>
            </>
          )}
        </>
      )}
    </section>
  )
}

export default function LiveSessionPage() {
  const { sessionId } = useParams()
  const numericId = Number(sessionId)

  if (
    !/^[1-9][0-9]*$/.test(sessionId || '') ||
    !Number.isSafeInteger(numericId)
  ) {
    return (
      <section className="qp-content">
        <h1>Invalid session ID</h1>
        <Link to="/app/dashboard/present">Return to dashboard</Link>
      </section>
    )
  }

  return (
    <ConnectedSession
      key={sessionId}
      sessionId={sessionId}
    />
  )
}
