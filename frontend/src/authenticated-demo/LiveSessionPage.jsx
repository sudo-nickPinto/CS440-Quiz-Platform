import { useEffect, useState } from "react";
import { Link, Navigate, useParams } from "react-router";

import { useLiveSession } from "../live/useLiveSession";
import { useAction, useResource } from "./rest";
import RequestError from "./RequestError";

const CONNECTION_ERRORS = {
  unauthorized: "Your login needs to be renewed.",
  forbidden: "You cannot access this session.",
  not_found: "This session does not exist.",
  replaced: "This session was opened elsewhere using the same account.",
  failed: "The live connection failed.",
  closed: "The live connection is closed.",
};

function letter(index) {
  return index < 26 ? String.fromCharCode(65 + index) : String(index + 1);
}

function Dots() {
  return (
    <span className="ui-dots" aria-hidden="true">
      <i />
      <i />
      <i />
    </span>
  );
}

function Score({ label, value }) {
  return (
    <div className="ui-score">
      <span>{label}</span>
      <strong>{value ?? "—"}</strong>
    </div>
  );
}

function Leaderboard({ rows }) {
  return (
    <section className="ui-board" aria-label="Current leaderboard">
      <div className="ui-titlebar">
        <span>Leaderboard</span>
        <span>Current standings</span>
      </div>

      {!rows.length ? (
        <p className="ui-message">No standings available yet.</p>
      ) : (
        <ol>
          {rows.map((row) => (
            <li key={row.session_participant_id}>
              <strong className="ui-rank">{row.rank}</strong>
              <span>{row.display_name}</span>
              <strong>
                {row.cumulative_score.toLocaleString()} pts
              </strong>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

function HostLobby({ state, title }) {
  const code = String(state.session.join_code || "");
  const formattedCode =
    code.length === 6 ? `${code.slice(0, 3)} ${code.slice(3)}` : code;

  return (
    <section className="ui-panel">
      <div className="ui-lobby-top">
        <p className="ui-eyebrow">Live session · Waiting room</p>
        <h1>{title}</h1>

        <div className="ui-join-row">
          <p>
            Open <strong>{window.location.host}/app/join</strong>
            <br />
            and enter the code
          </p>

          <div className="ui-join-code">
            <span>Join code</span>
            <strong>{formattedCode || "Loading…"}</strong>
          </div>

          <Score label="Players" value={state.participantCount} />
        </div>
      </div>

      <div className="ui-titlebar">
        <span>Players</span>
        <span>Lobby open</span>
      </div>

      <div className="ui-player-chips">
        {state.participants.map((person) => (
          <span key={person.session_participant_id}>
            {person.display_name}
          </span>
        ))}

        {!state.participants.length && (
          <p>
            {state.participantCount
              ? `${state.participantCount} players joined. Loading names…`
              : "Waiting for players to join…"}
          </p>
        )}
      </div>
    </section>
  );
}

function ParticipantLobby({ state, title }) {
  return (
    <section className="ui-participant-lobby">
      <div>
        <p className="ui-eyebrow">Live session</p>
        <h1>
          You’re <span className="ui-highlight">in!</span>
        </h1>

        <div className="ui-panel">
          <div className="ui-titlebar">Live quiz</div>
          <div className="ui-message">
            <h2>{title}</h2>
            <p>{state.session.total_questions} questions</p>
          </div>
        </div>

        <p className="ui-waiting" role="status">
          <Dots />
          Waiting for the host to start…
        </p>
      </div>

      <div className="ui-panel">
        <div className="ui-titlebar">
          <span>Players</span>
          <span>Lobby open</span>
        </div>
        <div className="ui-lobby-total">
          <strong>{state.participantCount}</strong>
          <span>players joined</span>
        </div>
      </div>
    </section>
  );
}

function QuestionScreen({ state, host, busy, canAct, submit }) {
  const question = state.currentQuestion;
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 250);
    return () => window.clearInterval(timer);
  }, []);

  const deadline = Date.parse(question.closes_at);
  const opened = Date.parse(question.opened_at);
  const seconds = Number.isFinite(deadline)
    ? Math.max(0, Math.ceil((deadline - now) / 1000))
    : null;

  const duration = deadline - opened;
  const progress =
    Number.isFinite(duration) && duration > 0
      ? Math.max(0, Math.min(100, ((deadline - now) / duration) * 100))
      : 0;

  const submittedIndex = question.choices.findIndex(
    (choice) => choice.choice_id === state.myAnswer?.choice_id,
  );

  if (!host && state.myAnswer) {
    return (
      <section className="ui-centered" aria-label="Answer submitted">
        <p className="ui-eyebrow">Your answer</p>
        <div className="ui-answer-stamp">
          {submittedIndex >= 0 ? letter(submittedIndex) : "✓"}
        </div>
        <h1>Answer submitted!</h1>
        <p role="status">Waiting for the question to close…</p>
        <Dots />
      </section>
    );
  }

  return (
    <section
      className={`ui-question ${host ? "ui-host-question" : "ui-player-question"}`}
      aria-label={`Question ${question.question_order}`}
    >
      <div className="ui-question-top">
        <div className="ui-timer" role="timer" aria-label="Seconds remaining">
          {seconds ?? "—"}
        </div>

        <div>
          <p className="ui-eyebrow">
            Question {question.question_order} of {question.total_questions}
          </p>

          {host ? (
            <h1>{question.question_text}</h1>
          ) : (
            <>
              <h1>Choose your answer</h1>
              <p>The question is on the host’s screen.</p>
            </>
          )}
        </div>

        {host && (
          <Score
            label="Answers"
            value={
              state.answerProgress
                ? `${state.answerProgress.answered_count}/${state.answerProgress.eligible_count}`
                : "—"
            }
          />
        )}
      </div>

      <div className="ui-time-track" aria-hidden="true">
        <div style={{ width: `${progress}%` }} />
      </div>

      <div
        className="ui-answer-grid"
        role={host ? undefined : "group"}
        aria-label={host ? undefined : "Answer choices"}
      >
        {question.choices.map((choice, index) =>
          host ? (
            <div
              key={choice.choice_id}
              className={`ui-answer ui-tone-${index % 4}`}
            >
              <span className="ui-letter">{letter(index)}</span>
              <span>{choice.choice_text}</span>
            </div>
          ) : (
            <button
              key={choice.choice_id}
              type="button"
              className={`ui-answer ui-tone-${index % 4}`}
              disabled={!canAct || seconds === 0}
              aria-label={`Answer ${letter(index)}`}
              onClick={() => submit(choice.choice_id)}
            >
              {letter(index)}
            </button>
          ),
        )}
      </div>

      {busy && !host && (
        <p className="ui-message" role="status">
          Submitting your answer…
        </p>
      )}

      {seconds === 0 && (
        <p className="ui-message" role="status">
          Waiting for the server to close the question…
        </p>
      )}
    </section>
  );
}

function HostQuestionResults({ question, results }) {
  const [showBoard, setShowBoard] = useState(false);

  if (!results) {
    return <p role="status">Loading question results…</p>;
  }

  const choices = question.choices.map((choice, index) => {
    const result = results.choices?.find(
      (item) => item.choice_id === choice.choice_id,
    );

    return {
      ...choice,
      label: letter(index),
      count: result?.response_count ?? 0,
      correct:
        result?.is_correct ||
        results.correct_choice_ids?.includes(choice.choice_id),
    };
  });

  const maximum = Math.max(1, ...choices.map((choice) => choice.count));

  return (
    <section>
      <div className="ui-results-heading">
        <p className="ui-eyebrow">
          Question {question.question_order} results
        </p>
        <h1>
          {showBoard ? "The leaderboard" : "How did everyone answer?"}
        </h1>
        <p>{question.question_text}</p>
      </div>

      {showBoard ? (
        <Leaderboard rows={results.participants || []} />
      ) : (
        <div className="ui-distribution">
          {choices.map((choice) => (
            <div
              key={choice.choice_id}
              className={`ui-distribution-column ${choice.correct ? "is-correct" : ""}`}
            >
              <strong>{choice.count}</strong>

              <div className="ui-bar-space" aria-hidden="true">
                <div
                  style={{
                    height: `${(choice.count / maximum) * 100}%`,
                  }}
                />
              </div>

              <div className="ui-distribution-label">
                <strong>{choice.label}</strong>
                <span>{choice.choice_text}</span>
                {choice.correct && <b>✓ Correct</b>}
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="ui-controls">
        <button
          type="button"
          onClick={() => setShowBoard((value) => !value)}
        >
          {showBoard ? "← Answer distribution" : "Show leaderboard →"}
        </button>
      </div>
    </section>
  );
}

function ParticipantFeedback({ question, results }) {
  if (!results) {
    return <p role="status">Loading your result…</p>;
  }

  const me = results.me;
  const selectedIndex = question.choices.findIndex(
    (choice) => choice.choice_id === me?.selected_choice_id,
  );
  const selected = question.choices[selectedIndex];
  const correct = question.choices.filter((choice) =>
    results.correct_choice_ids?.includes(choice.choice_id),
  );

  return (
    <section className="ui-centered">
      <div className={`ui-feedback-mark ${me?.is_correct ? "is-correct" : ""}`}>
        {me?.is_correct ? "✓" : "—"}
      </div>

      <h1>
        {!me
          ? "No individual result"
          : me.selected_choice_id == null
            ? "No answer recorded"
            : me.is_correct
              ? "Correct!"
              : "Not quite"}
      </h1>

      {selected && (
        <p>
          You picked <strong>{letter(selectedIndex)} · {selected.choice_text}</strong>
        </p>
      )}

      {correct.length > 0 && (
        <p>
          Correct answer:{" "}
          <strong>
            {correct.map((choice) => choice.choice_text).join(" / ")}
          </strong>
        </p>
      )}

      {me && (
        <>
          <div className="ui-points">+{me.points_awarded} points</div>
          <div className="ui-score-row">
            <Score label="Score" value={me.cumulative_score} />
            <Score label="Rank" value={me.rank == null ? "—" : `#${me.rank}`} />
          </div>
        </>
      )}

      <p role="status">Look at the host’s screen. The next question will appear here.</p>
      <Dots />
    </section>
  );
}

function ConnectedSession({ sessionId }) {
  const live = useLiveSession(sessionId);
  const action = useAction();
  const { state, phase } = live;

  // Optional metadata. Live state and controls still come from the socket.
  const metadata = useResource(
    state.session ? `/sessions/${sessionId}` : null,
  );

  const host = state.role === "host";
  const canAct = state.connection === "open" && !action.busy;
  const title = metadata.data?.quiz_title || `Session ${sessionId}`;
  const dashboard = `/app/dashboard/${host ? "present" : "participate"}`;
  const terminalMessage = CONNECTION_ERRORS[state.connection];

  const canAdvance =
    canAct &&
    host &&
    live.nextQuestionOrder !== null &&
    state.participantCount > 0 &&
    (
      phase === "lobby" ||
      phase === "waiting" ||
      (phase === "results" && Boolean(state.lastResults))
    );

  function run(command) {
    void action.run(command);
  }

  function confirmAndRun(message, command) {
    if (window.confirm(message)) run(command);
  }

  if (phase === "ended") {
    const view =
      host || Array.isArray(state.final?.standings) ? "host" : "me";

    return (
      <Navigate
        to={`/app/results/${view}/${sessionId}`}
        replace
      />
    );
  }

  return (
    <section className="ui-live">
      <div className="ui-titlebar">
        <strong>{host ? "Presenter" : "Participant"} · {title}</strong>
        <span>
          {phase} · {state.connection}
        </span>
      </div>

      <div className="ui-live-body">
        <Link to={dashboard}>← Dashboard</Link>

        <RequestError
          error={
            terminalMessage
              ? {
                  message: terminalMessage,
                  status: state.connection === "unauthorized" ? 401 : undefined,
                }
              : null
          }
          retry={
            ["replaced", "failed", "closed"].includes(state.connection)
              ? () => window.location.reload()
              : undefined
          }
        />

        {!terminalMessage && (
          <>
            {state.connection === "reconnecting" && (
              <p className="qp-notice" role="status">
                Reconnecting… Controls are paused until the connection returns.
              </p>
            )}

            {!host && state.session && !state.hostConnected && (
              <p className="qp-notice" role="status">
                The host disconnected. An open question still follows the server timer.
              </p>
            )}

            {phase === "connecting" && (
              <div className="ui-centered" role="status">
                <h1>Connecting…</h1>
                <Dots />
              </div>
            )}

            {phase === "left" && (
              <div className="ui-centered">
                <h1>You left the session</h1>
                <Link className="qp-button" to="/app/dashboard/participate">
                  Back to dashboard
                </Link>
              </div>
            )}

            {phase === "lobby" && state.session && (
              host
                ? <HostLobby state={state} title={title} />
                : <ParticipantLobby state={state} title={title} />
            )}

            {phase === "question" && state.currentQuestion && (
              <QuestionScreen
                key={state.currentQuestion.session_question_id}
                state={state}
                host={host}
                busy={action.busy}
                canAct={canAct}
                submit={(choiceId) =>
                  run(() => live.submitAnswer(choiceId))
                }
              />
            )}

            {phase === "results" && state.lastQuestion && (
              host ? (
                <HostQuestionResults
                  key={state.lastQuestion.session_question_id}
                  question={state.lastQuestion}
                  results={state.lastResults}
                />
              ) : (
                <ParticipantFeedback
                  question={state.lastQuestion}
                  results={state.lastResults}
                />
              )
            )}

            {phase === "waiting" && (
              <div className="ui-centered">
                <h1>Get ready!</h1>
                <p role="status">Waiting for the next question…</p>
                <Dots />
              </div>
            )}

            {state.session && !["left", "connecting"].includes(phase) && (
              <div className="ui-controls">
                {host ? (
                  <>
                    {state.session.status === "LOBBY" && (
                      <button
                        type="button"
                        disabled={!canAct}
                        onClick={() =>
                          confirmAndRun("Cancel this lobby for everyone?", live.cancel)
                        }
                      >
                        Cancel session
                      </button>
                    )}

                    {state.session.status === "ACTIVE" && (
                      <button
                        type="button"
                        disabled={!canAct}
                        onClick={() =>
                          confirmAndRun(
                            "End this session and save the final results?",
                            live.end,
                          )
                        }
                      >
                        End session
                      </button>
                    )}

                    {phase === "question" && (
                      <button
                        className="qp-primary"
                        type="button"
                        disabled={!canAct}
                        onClick={() => run(live.skip)}
                      >
                        Close question
                      </button>
                    )}

                    {["lobby", "waiting", "results"].includes(phase) &&
                      live.nextQuestionOrder !== null && (
                        <button
                          className="qp-primary"
                          type="button"
                          disabled={!canAdvance}
                          onClick={() => run(live.openNextQuestion)}
                        >
                          {phase === "lobby" ? "Start quiz →" : "Next question →"}
                        </button>
                      )}

                    {phase === "results" && live.nextQuestionOrder === null && (
                      <p>All questions are complete. Select End session to view the final report.</p>
                    )}
                  </>
                ) : (
                  <button
                    type="button"
                    disabled={!canAct}
                    onClick={() =>
                      confirmAndRun("Leave this session?", live.leave)
                    }
                  >
                    Leave session
                  </button>
                )}
              </div>
            )}

            {action.busy && (
              <p role="status">Waiting for server confirmation…</p>
            )}

            <RequestError error={action.error} />
          </>
        )}
      </div>
    </section>
  );
}

export default function LiveSessionPage() {
  const { sessionId } = useParams();
  const valid =
    /^[1-9][0-9]*$/.test(sessionId || "") &&
    Number.isSafeInteger(Number(sessionId));

  if (!valid) {
    return (
      <section className="qp-content">
        <h1>Invalid session ID</h1>
        <Link to="/app/dashboard/present">Back to dashboard</Link>
      </section>
    );
  }

  return <ConnectedSession key={sessionId} sessionId={sessionId} />;
}
