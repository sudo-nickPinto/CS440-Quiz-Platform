import { useState } from "react";
import { Link, useParams } from "react-router";

import RequestError from "./RequestError";
import { useResource } from "./rest";
import "./quiz-history.css";

const PAGE_SIZE = 20;

function displayDate(value) {
  if (!value) return "Date unavailable";

  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "Date unavailable"
    : date.toLocaleString();
}

// The class-admin mockup's date block: "OCT / 19"
function DateBlock({ value }) {
  const date = value ? new Date(value) : null;
  const valid = date && !Number.isNaN(date.getTime());

  return (
    <span className="qh-date" aria-hidden="true">
      <small>
        {valid ? date.toLocaleString(undefined, { month: "short" }) : "—"}
      </small>
      <b>{valid ? String(date.getDate()).padStart(2, "0") : "—"}</b>
    </span>
  );
}

function HistoryList({ endpoint, host, backTo }) {
  const [page, setPage] = useState(0);

  const resource = useResource(
    `${endpoint}?limit=${PAGE_SIZE}&offset=${page * PAGE_SIZE}`,
  );

  const items = resource.data?.items ?? [];
  const quizTitle = items[0]?.quiz_title;

  return (
    <section className="qh" aria-label={host ? "Hosting history" : "Quizzes taken"}>
      <header className="qe-bar qh-bar">
        <Link className="qe-back" to={backTo}>
          <span aria-hidden="true">←</span>
          <span className="qe-back-word">Quiz</span>
          <span className="ui-sr">Back to the quiz</span>
        </Link>

        <div className="qe-titlebox">
          <span className="qe-eyebrow">
            {host ? "Hosting history" : "Quizzes taken"}
          </span>
          <h1 className="qv-title">
            {quizTitle || (host ? "Hosting history" : "Quizzes taken")}
          </h1>
          <p className="qv-description">
            {host
              ? "Each row is a separate live session of this quiz."
              : "Revisit your answers and results from completed quizzes."}
          </p>
        </div>

        <div className="qe-state">
          <button
            type="button"
            className="ui-linkbtn"
            disabled={resource.loading}
            onClick={resource.reload}
          >
            Refresh
          </button>
        </div>
      </header>

      <div className="qh-head" aria-hidden="true">
        <span>Date</span>
        <span>Session</span>
        <span className="qh-wide">Status</span>
        <span />
      </div>

      {resource.loading && (
        <p className="qh-message" role="status">
          Loading history…
        </p>
      )}

      <RequestError error={resource.error} retry={resource.reload} />

      {!resource.loading && !resource.error && (
        <>
          {!items.length && (
            <div className="qh-message">
              <h2>
                {page > 0
                  ? "No sessions on this page"
                  : host
                    ? "No past sessions yet"
                    : "No completed quizzes yet"}
              </h2>

              <p>
                {host
                  ? "Completed and cancelled sessions of this quiz will appear here."
                  : "After a quiz you joined ends, your report will appear here."}
              </p>

              {!host && page === 0 && (
                <Link className="qp-button" to="/app/join">
                  Join a quiz
                </Link>
              )}
            </div>
          )}

          <div className="qh-list">
            {items.map((session) => {
              const cancelled = session.status === "CANCELLED";
              const when =
                session.ended_at ?? session.started_at ?? session.created_at;

              return (
                <article
                  className={"qh-row" + (cancelled ? " is-cancelled" : "")}
                  key={session.session_id}
                >
                  <DateBlock value={when} />

                  <div className="qh-main">
                    <strong>Session #{session.session_id}</strong>
                    <small>
                      Version {session.version_number}
                      {" · "}
                      Hosted by {session.host_name}
                    </small>
                    <small>
                      {cancelled ? "Cancelled" : "Completed"}:{" "}
                      {displayDate(when)}
                    </small>
                  </div>

                  <span className="qh-wide">
                    <span
                      className={"qh-status" + (cancelled ? " is-cancelled" : "")}
                    >
                      {cancelled ? "Cancelled" : "Completed"}
                    </span>
                  </span>

                  {cancelled ? (
                    <span className="qh-note">No results</span>
                  ) : (
                    <Link
                      className="qh-go"
                      to={`/app/results/${host ? "host" : "me"}/${session.session_id}`}
                      aria-label={`View report for session ${session.session_id}`}
                    >
                      <span aria-hidden="true">→</span>
                    </Link>
                  )}
                </article>
              );
            })}
          </div>
        </>
      )}

      <nav className="qh-pagination" aria-label="History pages">
        <button
          type="button"
          disabled={page === 0 || resource.loading}
          onClick={() => setPage((current) => Math.max(0, current - 1))}
        >
          ← Previous
        </button>

        <span aria-live="polite">Page {page + 1}</span>

        <button
          type="button"
          disabled={
            resource.loading ||
            Boolean(resource.error) ||
            !resource.data?.has_more
          }
          onClick={() => setPage((current) => current + 1)}
        >
          Next →
        </button>
      </nav>
    </section>
  );
}


export function QuizHostingHistory() {
  const { quizId } = useParams();

  const valid =
    /^[1-9][0-9]*$/.test(quizId ?? "") &&
    Number.isSafeInteger(Number(quizId));

  if (!valid) {
    return <p className="qp-content" role="alert">Invalid quiz ID.</p>;
  }

  return (
    <HistoryList
      key={quizId}
      endpoint={`/quizzes/${quizId}/history`}
      backTo={`/app/quizzes/${quizId}`}
      host
    />
  );
}
