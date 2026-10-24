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

function AnswerDetail({ question, answer }) {
  return (
    <section className="rr-answer-detail">
      <div className="rr-panel-heading">
        <span>Question {question.order}</span>
        <span>
          {GLYPH[answer.state]} {LABEL[answer.state]} · {fmt(answer.points)} pts
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
                  (choice.correct ? "correct" : selected ? "wrong" : "")
                }
              >
                <b>{String.fromCharCode(65 + index)}</b>

                <div>
                  <strong>{choice.text}</strong>
                  <small>
                    {choice.correct ? "✓ Correct answer" : ""}
                    {selected
                      ? choice.correct
                        ? " · Selected answer"
                        : "✗ Selected answer"
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
            <small>Explanation</small>
            <p>{question.explanation || "No explanation was provided."}</p>
          </div>
        </div>

        {answer.state === "missed" && (
          <p>No answer was recorded for this question.</p>
        )}
      </div>
    </section>
  );
}

function PlayerAnswers({ report, player }) {
  return (
    <div className="rr-expanded">
      <div className="rr-panel-heading">{player.name} · Answer review</div>

      {report.questions.map((q, i) => {
        const answer = player.answers[i];
        const selected = q.choices.find((c) => c.id === answer.choice_id);
        const correct = q.choices
          .filter((c) => c.correct)
          .map((c) => c.text)
          .join(" / ");

        return (
          <div className="rr-answer-line" key={q.question_id}>
            <Mark answer={answer} order={q.order} />
            <strong>Q{q.order}</strong>

            <div>
              <strong>{q.text}</strong>
              <p>
                {selected ? "Selected: " + selected.text : LABEL[answer.state]}
              </p>
              <small>Correct: {correct}</small>
            </div>

            <span>{seconds(answer.time_ms)}</span>
            <strong>{fmt(answer.points)} pts</strong>
          </div>
        );
      })}
    </div>
  );
}

function People({ title, people, questionIndex, onPerson }) {
  const [expanded, setExpanded] = useState(false);
  const visible = expanded ? people : people.slice(0, 8);

  return (
    <section className="rr-people">
      <h4>
        {title} · {people.length}
      </h4>

      <div className="rr-chips">
        {visible.map((p) => (
          <button type="button" key={p.id} onClick={() => onPerson(p.id)}>
            {p.name}
            <span>{seconds(p.answers[questionIndex].time_ms)}</span>
          </button>
        ))}

        {!people.length && <p>None</p>}

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
      label:
        String.fromCharCode(65 + i) +
        ". " +
        choice.text +
        (choice.correct ? " — Correct" : ""),
      count: players.filter((p) => p.answers[index].choice_id === choice.id)
        .length,
      correct: choice.correct,
    })),
    {
      key: "missed",
      label: "No answer",
      count: byState("missed").length,
    },
  ];

  return (
    <details className="rr-question">
      <summary>
        <span className="rr-rank pale">Q{question.order}</span>
        <strong>{question.text}</strong>
        <span>{question.played ? percentage + "% correct" : "Not played"}</span>
      </summary>

      {!question.played ? (
        <p className="rr-padding">This question was not played.</p>
      ) : (
        <div className="rr-breakdown">
          <div className="rr-padding">
            <h3>Answer distribution</h3>
            <p>Counts include everyone who joined this session.</p>

            {groups.map((group) => (
              <div
                className={"rr-bar-row " + (group.correct ? "correct" : "")}
                key={group.key}
              >
                <strong>{group.label}</strong>
                <span>
                  {group.count} / {players.length}
                </span>
                <progress
                  value={group.count}
                  max={Math.max(1, players.length)}
                  aria-label={group.label}
                />
              </div>
            ))}
          </div>

          <div>
            <People
              title="Correct · fastest first"
              people={right}
              questionIndex={index}
              onPerson={onPerson}
            />
            <People
              title="Wrong"
              people={byState("wrong")}
              questionIndex={index}
              onPerson={onPerson}
            />
            <People
              title="No answer"
              people={byState("missed")}
              questionIndex={index}
              onPerson={onPerson}
            />
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

  return (
    <div className="rr">
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
          value={average("correct").toFixed(1) + " / " + report.played_count}
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
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label={questionsTab ? "Search questions" : "Search participants"}
          placeholder={
            questionsTab ? "Search questions…" : "Search participants…"
          }
        />
        <strong>
          {questionsTab ? filteredQuestions.length : filteredPlayers.length}{" "}
          shown
        </strong>
      </div>

      {questionsTab ? (
        <section aria-label="Question breakdowns">
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
          <div className="rr-list-heading">
            Rank · Participant · Answers · Correct · Points
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

                <span>
                  <b>{p.correct}</b> / {report.played_count} correct
                </span>
                <span>
                  <b>{fmt(p.points)}</b> pts
                </span>
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

  return (
    <div className="rr">
      <Title report={report} host={false} />

      <div className="rr-report-band">
        <Stat label="Speed points" value={fmt(player.points)} />
        <Stat
          label="Correct"
          value={player.correct + " / " + report.played_count}
        />
        <Stat label="Average answer time" value={seconds(average)} />
        <Stat
          label="Fastest correct"
          value={
            fastestQ
              ? "Q" + fastestQ.order + " · " + seconds(fastest.time_ms)
              : "—"
          }
        />
        <Stat
          label="Your rank"
          value={"#" + player.rank + " of " + report.total_participants}
        />
      </div>

      <p className="rr-padding">
        Your answers are shown here. The host and Admins can also review session
        results.
      </p>

      <div className="rr-reader">
        <section className="rr-answer-map" aria-label="Your answers">
          <div className="rr-panel-heading">Your answers</div>

          <p className="rr-padding">
            ✓ {count("correct")} correct · ✗ {count("wrong")} wrong · —{" "}
            {count("missed")} unanswered · {count("not_played")} not played
          </p>

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
                <strong>Q{q.order}</strong>
                <span>{GLYPH[player.answers[i].state]}</span>
                <small>{fmt(player.answers[i].points)} pts</small>
              </button>
            ))}
          </div>

          <p className="rr-padding">Select a question to review your answer.</p>
        </section>

        <div>
          {question && answer && (
            <AnswerDetail question={question} answer={answer} />
          )}

          <nav className="rr-question-nav" aria-label="Question navigation">
            <button
              type="button"
              disabled={selected === 0}
              onClick={() => selectQuestion(selected - 1)}
            >
              ← Previous
            </button>

            <button
              type="button"
              disabled={!question || selected >= report.questions.length - 1}
              onClick={() => selectQuestion(selected + 1)}
            >
              Next →
            </button>
          </nav>
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
