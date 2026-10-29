import { useEffect, useState } from "react";
import { Link, Navigate, useParams } from "react-router";

import { useLiveSession } from "../live/useLiveSession";
import { useAction, useResource } from "./rest";
import RequestError from "./RequestError";
import ConfirmDialog from "./ConfirmDialog";
import { useConfirm } from "./useConfirm";
import { HostFinal, ParticipantFinal } from "./LiveFinal";

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

// "482913" → "482 913", as on the mockup's projector screen
function spacedCode(code) {
  const text = String(code || "");
  return text.length === 6 ? `${text.slice(0, 3)} ${text.slice(3)}` : text;
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

// ■■□□□ progress marks (done · current · to come)
function Marks({ total, current }) {
  const count = Math.min(Number(total) || 0, 20);

  return (
    <span className="lv-marks" aria-hidden="true">
      {Array.from({ length: count }, (_, index) => (
        <i
          key={index}
          className={
            index + 1 < current ? "done" : index + 1 === current ? "cur" : ""
          }
        />
      ))}
    </span>
  );
}

function Stat({ label, value, small }) {
  return (
    <div className="lv-stat">
      <span>{label}</span>
      <strong>
        {value ?? "—"}
        {small && <small>{small}</small>}
      </strong>
    </div>
  );
}

function Leaderboard({ rows }) {
  if (!rows.length) {
    return <p className="lv-final-empty">No standings available yet.</p>;
  }

  return (
    <ol className="lv-board" aria-label="Current leaderboard">
      {rows.map((row, index) => (
        <li
          key={row.session_participant_id ?? `${row.rank}-${row.display_name}`}
          style={{ "--i": index }}
        >
          <span className="lv-rank">{row.rank}</span>
          <strong>{row.display_name}</strong>
          <span className="lv-pts">
            {row.cumulative_score.toLocaleString()} pts
          </span>
        </li>
      ))}
    </ol>
  );
}

function HostLobby({ state, title, actions }) {
  const code = spacedCode(state.session.join_code);
  const count = state.participantCount;

  return (
    <section className="lv-lobby">
      <div className="lv-card">
        <div className="lv-lobby-top">
          <p className="lv-eyebrow">Live session · Waiting room</p>
          <h1>{title}</h1>

          <div className="lv-join-row">
            <p className="lv-join-step">
              Go to <b>{window.location.host}/app/join</b>
              <br />
              and enter the code
            </p>

            <div className="lv-join-code">
              <small>Join code</small>
              {code || "Loading…"}
            </div>

            <div className="lv-count">
              <strong>{count}</strong>
              <span>{count === 1 ? "Player" : "Players"}</span>
            </div>
          </div>
        </div>

        <div className="qb-panel-top">
          <span>Players</span>
          <span>Late joiners welcome</span>
        </div>

        <div className="lv-players">
          {state.participants.map((person) => (
            <span className="lv-chip" key={person.session_participant_id}>
              {person.display_name}
            </span>
          ))}

          {!state.participants.length && (
            <div className="lv-players-empty">
              <span>
                {count
                  ? `${count} players joined. Loading names…`
                  : "Waiting for players to join…"}
              </span>
              <Dots />
            </div>
          )}
        </div>
      </div>

      {actions}
    </section>
  );
}

function ParticipantLobby({ state, title, actions }) {
  const code = spacedCode(state.session.join_code);
  const count = state.participantCount;

  return (
    <section className="lv-plobby">
      <div className="lv-plobby-main">
        <p className="lv-eyebrow">{code ? `Session ${code}` : "Live session"}</p>
        <h1>
          You’re <span className="ui-highlight">in!</span>
        </h1>

        <div className="lv-quizcard">
          <div className="lv-quizcard-top">Live quiz</div>
          <div className="lv-quizcard-body">
            <strong>{title}</strong>
            <p>
              {state.session.total_questions}{" "}
              {state.session.total_questions === 1 ? "question" : "questions"}
            </p>
          </div>
        </div>

        <p className="lv-wait" role="status">
          <Dots />
          Waiting for the host to start…
        </p>

        {actions}
      </div>

      <div className="lv-panel">
        <div className="qb-panel-top">
          <span>Players</span>
          <span>Lobby open</span>
        </div>
        <p className="lv-count-line">
          <strong>{count}</strong>
          <span>{count === 1 ? "player" : "players"} joined</span>
        </p>
      </div>
    </section>
  );
}

function QuestionScreen({ state, host, busy, canAct, submit, controls }) {
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
      <section className="lv-centered" aria-label="Answer submitted">
        <p className="lv-pick-label">Your answer</p>
        <div
          className={`lv-my-pick ui-tone-${Math.max(submittedIndex, 0) % 4}`}
        >
          {submittedIndex >= 0 ? letter(submittedIndex) : "✓"}
        </div>
        <h1>Answer submitted!</h1>
        <p role="status">Waiting for everyone else to answer…</p>
        <Dots />
      </section>
    );
  }

  if (host) {
    const answered = state.answerProgress?.answered_count ?? 0;
    const eligible =
      state.answerProgress?.eligible_count ?? state.participantCount;

    return (
      <section
        className="lv-hq"
        aria-label={`Question ${question.question_order}`}
      >
        <div className="lv-hq-top">
          <div
            className={"lv-timer" + (seconds !== null && seconds <= 5 ? " is-urgent" : "")}
            role="timer"
            aria-label="Seconds remaining"
          >
            {seconds ?? "—"}
          </div>

          <div className="lv-hq-text">
            <h1>{question.question_text}</h1>
          </div>

          <div className="lv-answer-count" aria-live="polite">
            <strong>
              {answered}
              <small>/{eligible}</small>
            </strong>
            <span>Answers</span>
          </div>
        </div>

        <div className="lv-track" aria-hidden="true">
          <div style={{ width: `${progress}%` }} />
        </div>

        <div className="lv-host-answers">
          {question.choices.map((choice, index) => (
            <div
              key={choice.choice_id}
              className={`lv-host-answer ui-tone-${index % 4}`}
            >
              <span className="lv-index">{letter(index)}</span>
              <span>{choice.choice_text}</span>
            </div>
          ))}
        </div>

        {seconds === 0 && (
          <p className="lv-note" role="status">
            Time’s up. Closing the question…
          </p>
        )}

        {controls}
      </section>
    );
  }

  const me = state.lastResults?.me;

  return (
    <section
      className="lv-pq"
      aria-label={`Question ${question.question_order}`}
    >
      <div className="lv-pq-top">
        <div className="lv-q-label">
          <span>
            Question {question.question_order} of {question.total_questions}
          </span>
          <Marks
            total={question.total_questions}
            current={question.question_order}
          />
          <small>The question is on the host’s screen.</small>
        </div>

        <div
          className={"lv-ptimer" + (seconds !== null && seconds <= 5 ? " is-urgent" : "")}
          role="timer"
          aria-label="Seconds remaining"
        >
          {seconds ?? "—"}
        </div>
      </div>

      <div className="lv-tbar" aria-hidden="true">
        <i style={{ width: `${progress}%` }} />
      </div>

      <div
        className="lv-ptiles"
        role="group"
        aria-label="Answer choices"
      >
        {question.choices.map((choice, index) => (
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
        ))}
      </div>

      <div className="lv-stat-row lv-pbottom">
        <Stat label="Score" value={(me?.cumulative_score ?? 0).toLocaleString()} />
        <Stat label="Rank" value={me?.rank == null ? "—" : `#${me.rank}`} />
      </div>

      {busy && (
        <p className="lv-note" role="status">
          Submitting your answer…
        </p>
      )}

      {seconds === 0 && (
        <p className="lv-note" role="status">
          Time’s up. Waiting for the server to close the question…
        </p>
      )}
    </section>
  );
}

function HostQuestionResults({ question, results, controls }) {
  const [showBoard, setShowBoard] = useState(false);

  if (!results) {
    return (
      <p className="lv-centered" role="status">
        Loading question results…
      </p>
    );
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
  const answered = choices.reduce((sum, choice) => sum + choice.count, 0);
  const correct = choices
    .filter((choice) => choice.correct)
    .reduce((sum, choice) => sum + choice.count, 0);
  const players = results.participants?.length ?? answered;
  const percent = answered ? Math.round((correct / answered) * 100) : 0;

  return (
    <section className="lv-results">
      <div className="lv-r-head">
        <p className="lv-eyebrow">
          {showBoard ? "After question" : "Question"} {question.question_order}{" "}
          of {question.total_questions}
        </p>
        <h1>{showBoard ? "Leaderboard" : "How did everyone answer?"}</h1>
        {!showBoard && <p className="lv-r-q">{question.question_text}</p>}
      </div>

      {showBoard ? (
        <div className="lv-board-wrap">
          <Leaderboard rows={results.participants || []} />
        </div>
      ) : (
        <div className="lv-dist" style={{ "--n": choices.length }}>
          {choices.map((choice, index) => (
            <div
              key={choice.choice_id}
              className={"lv-dist-col" + (choice.correct ? " is-correct" : "")}
            >
              <div className="lv-bar-area">
                <div
                  className="lv-dbar"
                  style={{ "--h": `${(choice.count / maximum) * 100}%` }}
                >
                  <span className="lv-bar-num">{choice.count}</span>
                </div>
              </div>

              <div className="lv-dist-label">
                <span className={`lv-index ui-tone-${index % 4}`}>
                  {choice.label}
                </span>
                <span className="lv-dl-text">{choice.choice_text}</span>
                {choice.correct && (
                  <span className="lv-check" aria-label="Correct">
                    ✓
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="lv-strip">
        <p className="lv-meta">
          <b>{answered}</b> of {players} answered · <b>{correct}</b> correct (
          {percent}%)
        </p>

        <div className="lv-strip-actions">
          <button
            type="button"
            className="qb-btn qb-btn-paper"
            onClick={() => setShowBoard((value) => !value)}
          >
            {showBoard ? "← Answers" : "Show leaderboard"}
          </button>

          {controls}
        </div>
      </div>
    </section>
  );
}

function ParticipantFeedback({ question, results }) {
  if (!results) {
    return (
      <p className="lv-centered" role="status">
        Loading your result…
      </p>
    );
  }

  const me = results.me;
  const selectedIndex = question.choices.findIndex(
    (choice) => choice.choice_id === me?.selected_choice_id,
  );
  const selected = question.choices[selectedIndex];
  const correct = question.choices
    .map((choice, index) => ({ ...choice, index }))
    .filter((choice) => results.correct_choice_ids?.includes(choice.choice_id));

  return (
    <section className="lv-centered lv-feedback">
      <div className={`lv-feedback-mark ${me?.is_correct ? "is-correct" : ""}`}>
        {me?.is_correct ? "✓" : me?.selected_choice_id == null ? "—" : "✗"}
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

      <p className="lv-picked">
        {selected && (
          <>
            You picked{" "}
            <b>
              {letter(selectedIndex)} · {selected.choice_text}
            </b>
          </>
        )}
        {correct.length > 0 && !me?.is_correct && (
          <>
            {selected ? " · " : ""}The answer was{" "}
            <b>
              {correct
                .map((choice) => `${letter(choice.index)} · ${choice.choice_text}`)
                .join(" / ")}
            </b>
          </>
        )}
      </p>

      {me && (
        <>
          <div className={"lv-points" + (me.points_awarded ? "" : " is-zero")}>
            +{me.points_awarded.toLocaleString()}
          </div>
          <div className="lv-stat-row">
            <Stat label="Score" value={me.cumulative_score.toLocaleString()} />
            <Stat label="Rank" value={me.rank == null ? "—" : `#${me.rank}`} />
          </div>
        </>
      )}

      <p className="lv-sub" role="status">
        Look at the host’s screen for the leaderboard.
      </p>
      <Dots />
    </section>
  );
}

function ConnectedSession({ sessionId }) {
  const live = useLiveSession(sessionId);
  const action = useAction();
  const confirmer = useConfirm();
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

  async function confirmAndRun(options, command) {
    if (await confirmer.confirm(options)) run(command);
  }

  const total = state.session?.total_questions;
  const order =
    state.currentQuestion?.question_order ??
    state.lastQuestion?.question_order ??
    null;

  if (phase === "ended") {
    const completed = state.final?.status === "COMPLETED";

    if (completed && host && Array.isArray(state.final.standings)) {
      return (
        <section className="ui-live">
          <div className="lv-bar">
            <strong>{title}</strong>
            <span className="lv-bar-label">Final results</span>
          </div>
          <HostFinal
            final={state.final}
            title={title}
            totalQuestions={total ?? "—"}
            sessionId={sessionId}
          />
        </section>
      );
    }

    if (completed && !host && "me" in state.final) {
      return (
        <section className="ui-live">
          <div className="lv-bar">
            <strong>{title}</strong>
            <span className="lv-bar-label">Complete</span>
          </div>
          <ParticipantFinal
            final={state.final}
            totalQuestions={total ?? "—"}
            sessionId={sessionId}
          />
        </section>
      );
    }

    const view =
      host || Array.isArray(state.final?.standings) ? "host" : "me";

    return (
      <Navigate
        to={`/app/results/${view}/${sessionId}`}
        replace
      />
    );
  }

  const code = spacedCode(state.session?.join_code);
  const where =
    phase === "lobby"
      ? "Lobby"
      : phase === "question" && order
        ? `Question ${order} of ${total}`
        : phase === "results" && order
          ? `Question ${order} results`
          : phase === "waiting"
            ? "Up next"
            : phase === "left"
              ? "Left"
              : "Connecting";

  const startOrNext =
    host &&
    ["lobby", "waiting", "results"].includes(phase) &&
    live.nextQuestionOrder !== null ? (
      <button
        className="qb-btn"
        type="button"
        disabled={!canAdvance}
        onClick={() => run(live.openNextQuestion)}
      >
        {phase === "lobby" ? "Start quiz →" : "Next question →"}
      </button>
    ) : null;

  const allDone =
    host && phase === "results" && live.nextQuestionOrder === null ? (
      <button
        type="button"
        className="qb-btn"
        disabled={!canAct}
        onClick={() =>
          void confirmAndRun(
            {
              label: "End session",
              title: "That was the last question.",
              message: "End the session and save the final results?",
              confirmLabel: "End session",
              cancelLabel: "Not yet",
            },
            live.end,
          )
        }
      >
        Finish quiz →
      </button>
    ) : null;

  const leave = (
    <button
      type="button"
      className="qb-btn qb-btn-paper lv-leave"
      disabled={!canAct}
      onClick={() =>
        void confirmAndRun(
          {
            label: "Leave session",
            title: "Leave this session?",
            message:
              "You can rejoin with the same code while the session is still open.",
            confirmLabel: "Leave",
            cancelLabel: "Stay",
          },
          live.leave,
        )
      }
    >
      Leave
    </button>
  );

  return (
    <section className={"ui-live lv" + (host ? " is-host" : " is-player")}>
      <ConfirmDialog confirmer={confirmer} />

      <div className="lv-bar">
        <strong>{title}</strong>

        <div className="lv-bar-right">
          <span className="lv-bar-label">
            {host && code && phase !== "left" ? (
              <>
                Code <b>{code}</b> · {where}
              </>
            ) : (
              where
            )}
          </span>

          {host && state.session?.status === "ACTIVE" && (
            <button
              type="button"
              className="lv-bar-btn"
              disabled={!canAct}
              onClick={() =>
                void confirmAndRun(
                  {
                    label: "End session",
                    title: "End the session now?",
                    message:
                      "The open question closes, results are saved, and everyone sees the final standings.",
                    confirmLabel: "End session",
                    cancelLabel: "Keep going",
                  },
                  live.end,
                )
              }
            >
              End session
            </button>
          )}
        </div>
      </div>

      <div className="lv-body">
        {terminalMessage && (
          <div className="lv-centered">
            <RequestError
              error={{
                message: terminalMessage,
                status: state.connection === "unauthorized" ? 401 : undefined,
              }}
              retry={
                ["replaced", "failed", "closed"].includes(state.connection)
                  ? () => window.location.reload()
                  : undefined
              }
            />
            <Link className="qb-btn qb-btn-paper" to={dashboard}>
              Back to dashboard
            </Link>
          </div>
        )}

        {!terminalMessage && (
          <>
            {state.connection === "reconnecting" && (
              <p className="lv-notice" role="status">
                Reconnecting… Controls are paused until the connection returns.
              </p>
            )}

            {!host && state.session && !state.hostConnected && (
              <p className="lv-notice" role="status">
                The host disconnected. An open question still follows the server timer.
              </p>
            )}

            {phase === "connecting" && (
              <div className="lv-centered" role="status">
                <h1>Connecting…</h1>
                <Dots />
              </div>
            )}

            {phase === "left" && (
              <div className="lv-centered">
                <h1>You left the session</h1>
                <Link className="qb-btn" to="/app/dashboard/participate">
                  Back to dashboard
                </Link>
              </div>
            )}

            {phase === "lobby" && state.session && (
              host ? (
                <HostLobby
                  state={state}
                  title={title}
                  actions={
                    <div className="lv-actions">
                      <button
                        type="button"
                        className="qb-btn qb-btn-paper"
                        disabled={!canAct}
                        onClick={() =>
                          void confirmAndRun(
                            {
                              label: "Cancel session",
                              title: "Cancel this lobby?",
                              message:
                                "Everyone who joined is sent back and nothing is recorded.",
                              confirmLabel: "Cancel lobby",
                              cancelLabel: "Keep it open",
                            },
                            live.cancel,
                          )
                        }
                      >
                        Cancel
                      </button>
                      {startOrNext}
                    </div>
                  }
                />
              ) : (
                <ParticipantLobby state={state} title={title} actions={leave} />
              )
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
                controls={
                  <div className="lv-strip">
                    <p className="lv-meta">
                      The question closes when time runs out or everyone answers.
                    </p>
                    <div className="lv-strip-actions">
                      <button
                        className="qb-btn"
                        type="button"
                        disabled={!canAct}
                        onClick={() => run(live.skip)}
                      >
                        Close question
                      </button>
                    </div>
                  </div>
                }
              />
            )}

            {phase === "results" && state.lastQuestion && (
              host ? (
                <HostQuestionResults
                  key={state.lastQuestion.session_question_id}
                  question={state.lastQuestion}
                  results={state.lastResults}
                  controls={startOrNext ?? allDone}
                />
              ) : (
                <ParticipantFeedback
                  question={state.lastQuestion}
                  results={state.lastResults}
                />
              )
            )}

            {phase === "waiting" && (
              <div className="lv-centered lv-ready">
                <p className="lv-eyebrow">Up next</p>
                <h1>
                  {live.nextQuestionOrder
                    ? `Question ${live.nextQuestionOrder} of ${total}`
                    : "Get ready!"}
                </h1>
                <Marks total={total} current={live.nextQuestionOrder ?? 0} />
                <p role="status">Get ready…</p>
                {host && <div className="lv-actions">{startOrNext}</div>}
              </div>
            )}

            {!host &&
              state.session &&
              !["left", "connecting", "lobby"].includes(phase) && (
                <div className="lv-foot">{leave}</div>
              )}

            {action.busy && (
              <p className="lv-note" role="status">
                Waiting for server confirmation…
              </p>
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
