import { useState } from "react";
import { readRemembered, writeRemembered } from "./remember";
import {
  Link,
  Navigate,
  useLocation,
  useParams,
  useSearchParams,
} from "react-router";
import { useAction, useApi, useResource } from "./rest";
import { classPagePath } from "../classes/classPaths";
import RequestError from "./RequestError";
import { useFileDownload } from "./useFileDownload";
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

function RescoreNotice({ report }) {
  if (!report.score_revision) return null;

  return (
    <aside className="rr-rescore-notice" role="status">
      <strong>Results updated</strong>
      <span>
        This session has been rescored {report.score_revision} {report.score_revision === 1 ? "time" : "times"}.
        {report.rescored_at
          ? ` Latest update: ${new Date(report.rescored_at).toLocaleString()}.`
          : ""}
      </span>
    </aside>
  );
}

function CorrectAnswerPanel({ report, question, onCorrected }) {
  const api = useApi();
  const previewAction = useAction();
  const applyAction = useAction();
  const current = question.choices.find((choice) => choice.correct);
  const [choiceId, setChoiceId] = useState("");
  const [reason, setReason] = useState("");
  const [preview, setPreview] = useState(null);
  const [complete, setComplete] = useState("");

  async function previewRescore(event) {
    event.preventDefault();
    setComplete("");
    const result = await previewAction.run(() =>
      api(
        `/sessions/${report.session_id}/questions/${question.session_question_id}/correction-preview?choice_id=${choiceId}`,
      ),
    );
    if (result) setPreview(result);
  }

  async function applyCorrection() {
    const result = await applyAction.run(() =>
      api(
        `/sessions/${report.session_id}/questions/${question.session_question_id}/correct-answer`,
        {
          method: "POST",
          body: JSON.stringify({
            choice_id: Number(choiceId),
            reason,
            expected_score_revision: preview.score_revision,
          }),
        },
      ),
    );
    if (!result) return;
    setPreview(null);
    setChoiceId("");
    setReason("");
    setComplete(`Question ${question.order} was corrected and all saved results were rescored.`);
    onCorrected?.();
  }

  const changedSelection = preview && Number(choiceId) !== preview.proposed_correct_choice.choice_id;

  return (
    <section className="rr-correction" aria-label={`Correct answer for question ${question.order}`}>
      <div>
        <small>Organizer correction</small>
        <h4>Correct the saved session</h4>
        <p>
          This changes only this completed presentation. The quiz and every other session stay unchanged.
        </p>
      </div>

      <form onSubmit={previewRescore}>
        <label>
          Correct answer
          <select
            value={choiceId}
            required
            onChange={(event) => {
              setChoiceId(event.target.value);
              setPreview(null);
            }}
          >
            <option value="">Select a replacement…</option>
            {question.choices
              .filter((choice) => choice.id !== current?.id)
              .map((choice) => (
                <option value={choice.id} key={choice.id}>
                  {letterOf(question.choices.indexOf(choice))}. {choice.text}
                </option>
              ))}
          </select>
        </label>

        <label>
          Reason for the audit log
          <textarea
            value={reason}
            required
            maxLength={500}
            rows={3}
            onChange={(event) => setReason(event.target.value)}
            placeholder="Explain why the saved answer key is being corrected."
          />
        </label>

        <button className="rr-button" type="submit" disabled={previewAction.busy || !choiceId || !reason.trim()}>
          {previewAction.busy ? "Calculating…" : "Preview rescore"}
        </button>
      </form>

      <RequestError error={previewAction.error || applyAction.error} />
      {complete && <p className="rr-correction-success" role="status">✓ {complete}</p>}

      {preview && !changedSelection && (
        <div className="rr-rescore-preview">
          <div className="rr-panel-heading">
            <span>Preview · no changes saved yet</span>
            <span>{preview.affected_response_count} affected responses</span>
          </div>
          <p className="rr-padding">
            Correct answer: <b>{preview.current_correct_choice.text}</b> → <b>{preview.proposed_correct_choice.text}</b>
          </p>

          {preview.affected_participants.length ? (
            <div className="rr-rescore-table" role="table" aria-label="Projected score changes">
              <div role="row" className="rr-rescore-row heading">
                <span role="columnheader">Participant</span>
                <span role="columnheader">Question</span>
                <span role="columnheader">Total</span>
                <span role="columnheader">Rank</span>
              </div>
              {preview.affected_participants.map((person) => (
                <div role="row" className="rr-rescore-row" key={person.session_participant_id}>
                  <strong role="cell">{person.display_name}</strong>
                  <span role="cell">{fmt(person.old_question_points)} → {fmt(person.new_question_points)}</span>
                  <span role="cell">{fmt(person.old_total_score)} → {fmt(person.new_total_score)}</span>
                  <span role="cell">#{person.old_rank} → #{person.new_rank}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="rr-padding">No participant score or rank would change.</p>
          )}

          <div className="rr-correction-confirm">
            <p>This action updates saved answers, totals, and ranks and records an audit entry.</p>
            <button type="button" className="rr-button orange" disabled={applyAction.busy} onClick={() => void applyCorrection()}>
              {applyAction.busy ? "Rescoring…" : "Confirm correction & rescore"}
            </button>
          </div>
        </div>
      )}
    </section>
  );
}

function Title({ report, host, children, backTo, backLabel }) {
  const destination =
    backTo || "/app/classes";

  const label = backLabel || "Classes";

  return (
    <header className="rr-title">
      <Link className="rr-button" to={destination}>
        ← {label}
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

function QuestionBreakdown({ question, index, players, onPerson, report, onCorrected }) {
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

            {report.can_correct && question.session_question_id && (
              <CorrectAnswerPanel
                report={report}
                question={question}
                onCorrected={onCorrected}
              />
            )}
          </div>
        </div>
      )}
    </details>
  );
}

/*
 * The export defaults to the host's CSV. The class report passes the
 * class session's Excel export instead.
 */
export function HostResults({
  report,
  backTo,
  backLabel,
  exportPath = `/sessions/${report.session_id}/results/export.csv`,
  exportName = `session-${report.session_id}-results.csv`,
  exportLabel = "Export CSV",
  onCorrected,
}) {
  const [params, setParams] = useSearchParams();
  const [query, setQuery] = useState("");
  const file = useFileDownload();

  // ?tab= wins; otherwise the tab last open on this report.
  const tabMemory = `results:${exportPath}:tab`;
  const questionsTab =
    (params.get("tab") ?? readRemembered(tabMemory)) === "questions";
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
    writeRemembered(tabMemory, tab);
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

  const shown = questionsTab ? filteredQuestions.length : filteredPlayers.length;

  return (
    <div className="rr" style={{ "--q": report.questions.length }}>
      <Title report={report} host backTo={backTo} backLabel={backLabel}>
        <button
          type="button"
          className="rr-button orange"
          disabled={file.busy}
          onClick={() => void file.download(exportPath, exportName)}
        >
          {file.busy ? "Preparing…" : exportLabel}
        </button>
      </Title>

      <RequestError error={file.error} />
      <RescoreNotice report={report} />

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
              report={report}
              onCorrected={onCorrected}
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

export function ParticipantResults({ report, backTo, backLabel }) {
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
        <Link
          className="rr-crumb-back"
          to={backTo || "/app/classes"}
        >
          ← {backLabel || "Classes"}
        </Link>
        <div className="rr-trail">
          <span>Classes /</span>
          <span>Results /</span>
          <b>{report.quiz_title}</b>
        </div>
        <div className="rr-private">You, the host &amp; admins</div>
      </nav>

      <RescoreNotice report={report} />

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

  // The report doesn't say which class the session was in; the session
  // itself does. "Back" always goes to that class.
  const session = useResource(valid ? "/sessions/" + sessionId : null);
  const classId = session.data?.class_id;
  const back = classId
    ? { backTo: classPagePath(classId), backLabel: "Class" }
    : {};

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
        <Link to="/app/classes">Back to classes</Link>
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
        <Title report={report} host={host} {...back} />
        <p className="rr-padding">
          This session was cancelled. No quiz results were recorded.
        </p>
      </div>
    );
  }

  return host ? (
    <HostResults report={report} onCorrected={resource.reload} {...back} />
  ) : (
    <ParticipantResults report={report} {...back} />
  );
}
