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

function HistoryList({ endpoint, host }) {
  const [page, setPage] = useState(0);

  const resource = useResource(
    `${endpoint}?limit=${PAGE_SIZE}&offset=${page * PAGE_SIZE}`,
  );

  const items = resource.data?.items ?? [];

  return (
    <section className="qh" aria-label={host ? "Hosting history" : "Quizzes taken"}>
      <header className="qh-heading">
        <div>
          <p className="ui-eyebrow">
            {host ? "Presenter" : "Participant"}
          </p>

          <h1>{host ? "Hosting history" : "Quizzes taken"}</h1>

          <p>
            {host
              ? "Each entry is a separate live session of this quiz."
              : "Revisit your answers and results from completed quizzes."}
          </p>
        </div>

        <button
          type="button"
          disabled={resource.loading}
          onClick={resource.reload}
        >
          Refresh
        </button>
      </header>

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
                  ? "Completed and cancelled hosting sessions will appear here."
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

              return (
                <article className="qh-card" key={session.session_id}>
                  <div>
                    <span className="qh-status">
                      {cancelled ? "Cancelled" : "Completed"}
                    </span>

                    <h2>{session.quiz_title}</h2>

                    <p>
                      Session #{session.session_id}
                      {" · "}
                      Version {session.version_number}
                    </p>

                    <p>Hosted by {session.host_name}</p>

                    <p>
                      {cancelled ? "Cancelled" : "Completed"}:{" "}
                      {displayDate(
                        session.ended_at ??
                          session.started_at ??
                          session.created_at,
                      )}
                    </p>
                  </div>

                  {cancelled ? (
                    <p className="qh-note">
                      No quiz results were recorded.
                    </p>
                  ) : (
                    <Link
                      className="qp-button"
                      to={`/app/results/${host ? "host" : "me"}/${session.session_id}`}
                    >
                      View report
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
    <div>
      <div className="qh-back">
        <Link className="qp-button" to="/app/dashboard/present">
          ← Present
        </Link>
      </div>

      <HistoryList
        key={quizId}
        endpoint={`/quizzes/${quizId}/history`}
        host
      />
    </div>
  );
}
