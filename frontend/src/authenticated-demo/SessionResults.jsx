import { useState } from "react";
import { useAuth0 } from "@auth0/auth0-react";
import {
  Link,
  Navigate,
  useLocation,
  useParams,
  useSearchParams,
} from "react-router";
import { useAction, useResource } from "./rest";
import RequestError from "./RequestError";
import "./session-results.css";

const LABEL = {
  correct: "Correct",
  wrong: "Wrong",
  missed: "No answer",
  not_played: "Not played",
};

const GLYPH = {
  correct: "✓",
  wrong: "✗",
  missed: "—",
  not_played: "·",
};

const fmt = (value) => Number(value).toLocaleString();

const seconds = (value) =>
  value == null ? "—" : (value / 1000).toFixed(1) + "s";

const letterOf = (index) => String.fromCharCode(65 + index);

function Mark({ answer, order }) {
  return (
    <span
      className={"rr-mark " + answer.state}
      title={"Q" + order + ": " + LABEL[answer.state]}
      aria-label={"Q" + order + ": " + LABEL[answer.state]}
    >
      {GLYPH[answer.state]}
    </span>
  );
}

function Stat({ label, value }) {
  return (
    <div className="rr-stat">
      <small>{label}</small>
      <strong>{value}</strong>
    </div>
  );
}

function Title({ report, host, children }) {
  return (
    <header className="rr-title">
      <Link
        className="rr-button"
        to={
          host
            ? `/app/quizzes/${report.quiz_id}/reports`
            : "/app/dashboard/participate"
        }
      >
        ← {host ? "Hosting history" : "Participate"}
      </Link>

      <div>
        <small>{host ? "Session results" : "Your report card"}</small>
        <h1>{report.quiz_title}</h1>
        <p>
          Hosted by {report.host_name} ·{" "}
          {report.ended_at
            ? new Date(report.ended_at).toLocaleString()
            : "Session ended"}
        </p>
      </div>

      {children}
    </header>
  );
}

function AnswerDetail({ question, answer, total, nav }) {
  return (
    <section className="rr-answer-detail" aria-live="polite">
      <div className="rr-panel-heading">
        <span>
          Question {question.order} of {total}
        </span>
        <span className="rr-detail-tools">
          <span className={"rr-result " + answer.state}>
            {GLYPH[answer.state]} {LABEL[answer.state]} · {fmt(answer.points)}{" "}
            pts
          </span>
          {nav}
        </span>
      </div>

      <div className="rr-detail-body">
        <h3>{question.text}</h3>

        {!question.played && (
          <p>This question was not played before the session ended.</p>
        )}

        <div className="rr-choices">
          {question.choices.map((choice, index) => {
            const selected = answer.choice_id === choice.id;

            return (
              <div
                key={choice.id}
                className={
                  "rr-choice " +
                  (choice.correct ? "correct" : selected ? "wrong" : "dim")
                }
              >
                <b>{letterOf(index)}</b>

                <div>
                  <strong>{choice.text}</strong>
                  <small>
                    {choice.correct && selected
                      ? "✓ Your answer · correct"
                      : choice.correct
                        ? "✓ Correct answer"
                        : selected
                          ? "✗ Your answer"
                          : ""}
                  </small>
                </div>
              </div>
            );
          })}
        </div>

        <div className="rr-facts">
          <Stat
            label={"Answer time · limit " + question.seconds + "s"}
            value={seconds(answer.time_ms)}
          />

          <Stat
            label={"Points · maximum " + fmt(question.base_points)}
            value={fmt(answer.points)}
          />

          <div className="rr-explanation">
            <small>Why</small>
            <p className={question.explanation ? "" : "rr-none"}>
              {question.explanation ||
                "The host didn’t add an explanation for this one."}
            </p>
          </div>
        </div>

        {answer.state === "missed" && (
          <p className="rr-missed-note">
            No answer was recorded. A missed question counts as 0 points.
          </p>
        )}
      </div>
    </section>
  );
}

function PlayerAnswers({ report, player }) {
  return (
    <div className="rr-expanded">
      <div className="rr-xp">
        <div className="rr-panel-heading">
          <span>{player.name}</span>
          <span>
            {player.correct}/{report.played_count} · {fmt(player.points)} pts
          </span>
        </div>

        <div className="rr-al-head" aria-hidden="true">
          <span />
          <span>Q</span>
          <span>Question · their answer</span>
          <span>Time</span>
          <span>Points</span>
        </div>

        {report.questions.map((q, i) => {
          const answer = player.answers[i];
          const selectedIndex = q.choices.findIndex(
            (c) => c.id === answer.choice_id,
          );
          const selected = q.choices[selectedIndex];
          const correct = q.choices
            .map((c, index) => ({ ...c, index }))
            .filter((c) => c.correct)
            .map((c) => letterOf(c.index) + ". " + c.text)
            .join(" / ");

          return (
            <div className="rr-answer-line" key={q.question_id}>
              <Mark answer={answer} order={q.order} />
              <strong>Q{q.order}</strong>

              <div>
                <strong>{q.text}</strong>
                <p>
                  {selected
                    ? letterOf(selectedIndex) + ". " + selected.text
                    : LABEL[answer.state]}
                </p>
                {answer.state !== "correct" && <small>Correct: {correct}</small>}
              </div>

              <span>{seconds(answer.time_ms)}</span>
              <strong>{fmt(answer.points)}</strong>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function People({ title, kind, people, questionIndex, onPerson }) {
  const [expanded, setExpanded] = useState(false);
  const visible = expanded ? people : people.slice(0, 8);

  return (
    <section className="rr-people">
      <h4>
        <span className={"rr-mark " + kind} aria-hidden="true">
          {GLYPH[kind]}
        </span>
        {title} · <b>{people.length}</b>
      </h4>

      <div className="rr-chips">
        {visible.map((p) => (
          <button type="button" key={p.id} onClick={() => onPerson(p.id)}>
            {p.name}
            {kind === "correct" && (
              <span>{seconds(p.answers[questionIndex].time_ms)}</span>
            )}
          </button>
        ))}

        {!people.length && <p>Nobody.</p>}

        {people.length > 8 && (
          <button type="button" onClick={() => setExpanded(!expanded)}>
            {expanded ? "Show fewer" : "+" + (people.length - 8) + " more"}
          </button>
        )}
      </div>
    </section>
  );
}

function QuestionBreakdown({ question, index, players, onPerson }) {
  const byState = (state) =>
    players.filter((p) => p.answers[index].state === state);

  const right = byState("correct").sort(
    (a, b) =>
      a.answers[index].time_ms - b.answers[index].time_ms || a.rank - b.rank,
  );

  const percentage = players.length
    ? Math.round((right.length / players.length) * 100)
    : 0;

  const groups = [
    ...question.choices.map((choice, i) => ({
      key: choice.id,
      letter: choice.correct ? "✓" : letterOf(i),
      label: letterOf(i) + ". " + choice.text,
      count: players.filter((p) => p.answers[index].choice_id === choice.id)
        .length,
      correct: choice.correct,
    })),
    {
      key: "missed",
      letter: "—",
      label: "No answer",
      count: byState("missed").length,
      missed: true,
    },
  ];

  const share = (count) =>
    players.length ? Math.round((count / players.length) * 100) : 0;

  return (
    <details className="rr-question">
      <summary>
        <span className="rr-rank pale">Q{question.order}</span>
        <strong>{question.text}</strong>
        <span className="rr-pct">
          {question.played ? (
            <>
              <span className="rr-meter" aria-hidden="true">
                <i style={{ width: percentage + "%" }} />
              </span>
              <b>{percentage}%</b>
              <span className="ui-sr"> correct</span>
            </>
          ) : (
            "Not played"
          )}
        </span>
        <i className="rr-tog" aria-hidden="true" />
      </summary>

      {!question.played ? (
        <p className="rr-padding">This question was not played.</p>
      ) : (
        <div className="rr-expanded">
          <div className="rr-xp">
            <div className="rr-panel-heading">
              <span>Q{question.order} · Answer split</span>
              <span>
                {right.length}/{players.length} correct
              </span>
            </div>

            <div className="rr-breakdown">
              <div className="rr-padding">
                {groups.map((group) => (
                  <div
                    className={
                      "rr-bar-row" +
                      (group.correct ? " correct" : "") +
                      (group.missed ? " is-missed" : "")
                    }
                    key={group.key}
                  >
                    <span className="rr-let" aria-hidden="true">
                      {group.letter}
                    </span>
                    <strong>
                      {group.label}
                      {group.correct && <em> Correct</em>}
                    </strong>
                    <span className="rr-track" aria-hidden="true">
                      <i style={{ width: share(group.count) + "%" }} />
                    </span>
                    <span className="rr-n">
                      <b>{share(group.count)}%</b>
                      <small>
                        {group.count} / {players.length}
                      </small>
                    </span>
                  </div>
                ))}
              </div>

              <div>
                <People
                  title="Got it right"
                  kind="correct"
                  people={right}
                  questionIndex={index}
                  onPerson={onPerson}
                />
                <People
                  title="Got it wrong"
                  kind="wrong"
                  people={byState("wrong")}
                  questionIndex={index}
                  onPerson={onPerson}
                />
                <People
                  title="No answer"
                  kind="missed"
                  people={byState("missed")}
                  questionIndex={index}
                  onPerson={onPerson}
                />
              </div>
            </div>
          </div>
        </div>
      )}
    </details>
  );
}

function HostResults({ report }) {
  const [params, setParams] = useSearchParams();
  const [query, setQuery] = useState("");
  const { getAccessTokenSilently } = useAuth0();
  const action = useAction();

  const questionsTab = params.get("tab") === "questions";
  const players = report.players;

  const average = (field) =>
    players.length
      ? players.reduce((sum, p) => sum + p[field], 0) / players.length
      : 0;

  const matches = (text) =>
    text.toLowerCase().includes(query.trim().toLowerCase());

  const filteredPlayers = players.filter((p) => matches(p.name));
  const filteredQuestions = report.questions.filter((q) => matches(q.text));

  function changeTab(tab) {
    setQuery("");
    setParams({ tab });
  }

  function showPerson(id) {
    setQuery("");
    setParams({ tab: "leaderboard", p: String(id) });

    window.requestAnimationFrame(() => {
      const row = document.getElementById("result-person-" + id);
      row?.querySelector("summary")?.focus();
      row?.scrollIntoView({ block: "nearest" });
    });
  }

  async function download() {
    const blob = await action.run(async () => {
      const token = await getAccessTokenSilently();
      const base = import.meta.env.VITE_API_BASE_URL.replace(/\/+$/, "");

      const response = await fetch(
        base + "/sessions/" + report.session_id + "/results/export.csv",
        {
          headers: { Authorization: "Bearer " + token },
        },
      );

      if (!response.ok) {
        const body = await response.json().catch(() => null);
        const error = new Error(body?.error?.message || "Export failed.");
        error.status = response.status;
        error.code = body?.error?.code;
        throw error;
      }

      return response.blob();
    });

    if (!blob) return;

    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "session-" + report.session_id + "-results.csv";

    document.body.appendChild(link);
    link.click();
    link.remove();

    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  const shown = questionsTab ? filteredQuestions.length : filteredPlayers.length;

  return (
    <div className="rr" style={{ "--q": report.questions.length }}>
      <Title report={report} host>
        <button
          type="button"
          className="rr-button orange"
          disabled={action.busy}
          onClick={() => void download()}
        >
          {action.busy ? "Preparing…" : "Export CSV"}
        </button>
      </Title>

      <RequestError error={action.error} />

      <div className="rr-summary">
        <Stat label="Participants" value={report.total_participants} />
        <Stat
          label="Average correct"
          value={
            <>
              {average("correct").toFixed(1)}
              <small> / {report.played_count}</small>
            </>
          }
        />
        <Stat
          label="Average points"
          value={fmt(Math.round(average("points")))}
        />
      </div>

      <nav className="rr-tabs" aria-label="Results view">
        <button
          type="button"
          aria-pressed={!questionsTab}
          onClick={() => changeTab("leaderboard")}
        >
          Leaderboard
        </button>
        <button
          type="button"
          aria-pressed={questionsTab}
          onClick={() => changeTab("questions")}
        >
          Questions
        </button>
      </nav>

      <div className="rr-toolbar">
        <input
          type="search"
          className="ui-search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label={questionsTab ? "Search questions" : "Search participants"}
          placeholder={
            questionsTab ? "Search questions…" : "Search participants…"
          }
        />
        <span className="ui-count" aria-live="polite">
          <strong>{shown}</strong>
          <span>
            {questionsTab
              ? shown === 1
                ? "question"
                : "questions"
              : shown === 1
                ? "player"
                : "players"}
          </span>
        </span>
      </div>

      {questionsTab ? (
        <section aria-label="Question breakdowns">
          <div className="rr-list-heading rr-q-head" aria-hidden="true">
            <span>#</span>
            <span>Question</span>
            <span>Correct</span>
            <span />
          </div>

          {filteredQuestions.map((q) => (
            <QuestionBreakdown
              key={q.question_id}
              question={q}
              index={report.questions.indexOf(q)}
              players={players}
              onPerson={showPerson}
            />
          ))}

          {!filteredQuestions.length && (
            <p className="rr-padding">No matching questions.</p>
          )}
        </section>
      ) : (
        <section aria-label="Leaderboard">
          <div className="rr-list-heading rr-lb-head" aria-hidden="true">
            <span>Rank</span>
            <span>Participant</span>
            <span className="rr-strip">
              {report.questions.map((q) => (
                <span key={q.question_id}>{q.order}</span>
              ))}
            </span>
            <span>Correct</span>
            <span>Points</span>
            <span />
          </div>

          {filteredPlayers.map((p) => (
            <details
              className="rr-player"
              id={"result-person-" + p.id}
              key={p.id + ":" + (params.get("p") === String(p.id))}
              open={params.get("p") === String(p.id) ? true : undefined}
            >
              <summary>
                <span className="rr-rank">{p.rank}</span>
                <strong className="rr-name">{p.name}</strong>

                <span className="rr-strip">
                  {p.answers.map((answer, i) => (
                    <Mark
                      key={answer.question_id}
                      answer={answer}
                      order={report.questions[i].order}
                    />
                  ))}
                </span>

                <span className="rr-correct">
                  <b>{p.correct}</b>
                  <small> / {report.played_count}</small>
                  <span className="ui-sr"> correct</span>
                </span>
                <span className="rr-points">
                  <b>{fmt(p.points)}</b>
                  <span className="ui-sr"> points</span>
                </span>
                <i className="rr-tog" aria-hidden="true" />
              </summary>

              <PlayerAnswers report={report} player={p} />
            </details>
          ))}

          {!filteredPlayers.length && (
            <p className="rr-padding">No matching participants.</p>
          )}
        </section>
      )}
    </div>
  );
}

function ParticipantResults({ report }) {
  const [params, setParams] = useSearchParams();
  const player = report.players[0];

  if (!player) {
    return <p className="rr-padding">No saved individual result was found.</p>;
  }

  const selected = Math.max(
    0,
    report.questions.findIndex(
      (q) => String(q.question_id) === params.get("q"),
    ),
  );

  const question = report.questions[selected];
  const answer = player.answers[selected];

  const answered = player.answers.filter((a) => a.time_ms !== null);

  const average = answered.length
    ? answered.reduce((sum, a) => sum + a.time_ms, 0) / answered.length
    : null;

  const fastest = player.answers
    .filter((a) => a.state === "correct")
    .sort((a, b) => a.time_ms - b.time_ms)[0];

  const fastestQ = report.questions.find(
    (q) => q.question_id === fastest?.question_id,
  );

  const count = (state) =>
    player.answers.filter((a) => a.state === state).length;

  function selectQuestion(index) {
    if (index >= 0 && index < report.questions.length) {
      setParams(
        { q: String(report.questions[index].question_id) },
        { replace: true },
      );
    }
  }

  const last = report.questions.length - 1;
  const nav = (
    <span className="rr-tbtns">
      <button
        type="button"
        disabled={selected === 0}
        aria-label="Previous question"
        onClick={() => selectQuestion(selected - 1)}
      >
        ← {selected === 0 ? "Prev" : "Q" + report.questions[selected - 1].order}
      </button>
      <button
        type="button"
        disabled={!question || selected >= last}
        aria-label="Next question"
        onClick={() => selectQuestion(selected + 1)}
      >
        {selected >= last ? "Next" : "Q" + report.questions[selected + 1].order}{" "}
        →
      </button>
    </span>
  );

  return (
    <div className="rr rr-me">
      <nav className="rr-crumbs" aria-label="Breadcrumb">
        <Link className="rr-crumb-back" to="/app/dashboard/participate">
          ← Participate
        </Link>
        <div className="rr-trail">
          <span>Dashboard /</span>
          <span>Results /</span>
          <b>{report.quiz_title}</b>
        </div>
        <div className="rr-private">You, the host &amp; admins</div>
      </nav>

      <div className="rr-me-content">
        <section className="rr-band" aria-label="Report card">
          <div className="rr-band-title">
            <small>Report card</small>
            <h1>{report.quiz_title}</h1>
            <p>
              Hosted by <b>{report.host_name}</b> ·{" "}
              {report.ended_at
                ? new Date(report.ended_at).toLocaleString()
                : "Session ended"}
            </p>
          </div>

          <div className="rr-bstat">
            <b>
              {fmt(player.points)}
              <small>pts</small>
            </b>
            <span>Speed points</span>
          </div>

          <div className="rr-bstat">
            <b>
              {player.correct}
              <small>/ {report.played_count}</small>
            </b>
            <span>
              Correct · {count("wrong")} wrong · {count("missed")} missed
            </span>
          </div>

          <div className="rr-bstat">
            <b>{seconds(average)}</b>
            <span>Avg. time</span>
          </div>

          <div className="rr-bstat">
            <b>
              {fastestQ ? (
                <>
                  Q{fastestQ.order}
                  <small>{seconds(fastest.time_ms)}</small>
                </>
              ) : (
                "—"
              )}
            </b>
            <span>Fastest right</span>
          </div>

          <div className="rr-bstat">
            <span className="rr-rank-tag">
              #{player.rank} <small>of {report.total_participants}</small>
            </span>
            <span>Your rank</span>
          </div>
        </section>

        <div className="rr-reader">
          <section className="rr-answer-map" aria-label="Your answers">
            <div className="rr-panel-heading">
              <span>Your answers</span>
              <span className="rr-key">
                <span aria-label={`${count("correct")} correct`}>
                  <i className="correct" aria-hidden="true">✓</i>
                  {count("correct")}
                </span>
                <span aria-label={`${count("wrong")} wrong`}>
                  <i className="wrong" aria-hidden="true">✗</i>
                  {count("wrong")}
                </span>
                <span aria-label={`${count("missed")} missed`}>
                  <i className="missed" aria-hidden="true">—</i>
                  {count("missed")}
                </span>
              </span>
            </div>

            <div className="rr-tiles">
              {report.questions.map((q, i) => (
                <button
                  type="button"
                  key={q.question_id}
                  className={"rr-tile " + player.answers[i].state}
                  aria-pressed={selected === i}
                  aria-label={
                    "Question " + q.order + ": " + LABEL[player.answers[i].state]
                  }
                  onClick={() => selectQuestion(i)}
                >
                  <span className="rr-tile-top">
                    <strong>Q{q.order}</strong>
                    <span>{GLYPH[player.answers[i].state]}</span>
                  </span>
                  <span className="rr-tile-bottom">
                    <small>
                      {player.answers[i].points
                        ? "+" + fmt(player.answers[i].points)
                        : "0"}
                    </small>
                    <small>
                      {player.answers[i].time_ms == null
                        ? LABEL[player.answers[i].state]
                        : seconds(player.answers[i].time_ms)}
                    </small>
                  </span>
                </button>
              ))}
            </div>

            <p className="rr-hint">
              Pick a question to see your answer and the correct one.
            </p>
          </section>

          <div>
            {question && answer && (
              <AnswerDetail
                question={question}
                answer={answer}
                total={report.questions.length}
                nav={nav}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default function SessionResults() {
  const { view, sessionId } = useParams();
  const { search } = useLocation();

  const valid =
    /^[1-9][0-9]*$/.test(sessionId || "") &&
    Number.isSafeInteger(Number(sessionId));

  const resource = useResource(
    valid
      ? "/sessions/" +
          sessionId +
          "/report" +
          (view === "me" ? "?personal=true" : "")
      : null,
  );

  if (!valid) return <p role="alert">Invalid session ID.</p>;

  if (resource.loading) {
    return (
      <p className="rr-padding" role="status">
        Loading saved results…
      </p>
    );
  }

  if (resource.error) {
    return (
      <section className="qp-content">
        <RequestError error={resource.error} retry={resource.reload} />
        <Link to="/app/dashboard/participate">Return to dashboard</Link>
      </section>
    );
  }

  const report = resource.data;
  if (!report) return null;

  const host = report.view === "host";
  const expectedView = host ? "host" : "me";

  if (view !== expectedView) {
    return (
      <Navigate
        to={"/app/results/" + expectedView + "/" + sessionId + search}
        replace
      />
    );
  }

  if (report.status === "CANCELLED") {
    return (
      <div className="rr">
        <Title report={report} host={host} />
        <p className="rr-padding">
          This session was cancelled. No quiz results were recorded.
        </p>
      </div>
    );
  }

  return host ? (
    <HostResults report={report} />
  ) : (
    <ParticipantResults report={report} />
  );
}
