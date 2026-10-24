import { useState } from "react";
import { Link } from "react-router";

import RequestError from "./RequestError";
import { useResource } from "./rest";
import "./participant-history.css";

const PAGE_SIZE = 20;

function displayDate(value) {
  if (!value) return "—";

  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "—"
    : date.toLocaleDateString();
}

export default function ParticipantHistory() {
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState("recent");
  const [page, setPage] = useState(0);

  const params = new URLSearchParams({
    limit: String(PAGE_SIZE),
    offset: String(page * PAGE_SIZE),
    q: query,
    sort,
  });

  const resource = useResource(`/me/sessions/taken?${params}`);
  const items = resource.data?.items ?? [];

  function changeQuery(value) {
    setQuery(value);
    setPage(0);
  }

  function changeSort(value) {
    setSort(value);
    setPage(0);
  }

  return (
    <section className="ph" aria-label="Quizzes taken">
      <div className="ui-toolbar">
        <input
          type="search"
          aria-label="Search quizzes taken"
          placeholder="Search quizzes…"
          maxLength={200}
          value={query}
          onChange={(event) => changeQuery(event.target.value)}
        />

        <details className="ui-filter">
          <summary>Filter{sort !== "recent" ? " •" : ""}</summary>

          <div className="ui-filter-panel">
            <label>
              Sort by
              <select
                value={sort}
                onChange={(event) => changeSort(event.target.value)}
              >
                <option value="recent">Most recent</option>
                <option value="score">Best score</option>
                <option value="az">A → Z</option>
              </select>
            </label>

            <p>Showing quizzes you participated in.</p>

            <button
              type="button"
              disabled={resource.loading}
              onClick={resource.reload}
            >
              Refresh
            </button>
          </div>
        </details>

        <span className="ui-count" aria-live="polite">
          <strong>{resource.loading ? "…" : items.length}</strong>
          <span>shown</span>
        </span>
      </div>

      <div className="ph-head" aria-hidden="true">
        <span>Rank</span>
        <span>Quiz</span>
        <span className="ph-score-column">Correct</span>
        <span className="ph-wide">Host</span>
        <span className="ph-wide">Date</span>
        <span>Review</span>
      </div>

      {resource.loading && (
        <p className="ui-empty" role="status">
          Loading your quizzes…
        </p>
      )}

      <RequestError error={resource.error} retry={resource.reload} />

      {!resource.loading && !resource.error && (
        <>
          {items.map((session) => {
            const hasScore = session.correct != null;
            const percentage =
              hasScore && session.played_count > 0
                ? Math.min(
                    100,
                    Math.max(
                      0,
                      (session.correct / session.played_count) * 100,
                    ),
                  )
                : 0;

            const score = hasScore
              ? `${session.correct}/${session.played_count}`
              : "Unavailable";

            return (
              <Link
                className="ph-row"
                key={session.session_id}
                to={`/app/results/me/${session.session_id}`}
                aria-label={`Review ${session.quiz_title}, session ${session.session_id}`}
              >
                <span className="ph-rank">
                  <strong>
                    {session.rank == null ? "—" : `#${session.rank}`}
                  </strong>
                  <small>of {session.total_participants}</small>
                </span>

                <span className="ph-title">
                  <strong>{session.quiz_title}</strong>
                  <small>
                    Session #{session.session_id}
                  </small>
                  <small className="ph-mobile-meta">
                    Hosted by {session.host_name}
                    {" · "}
                    {displayDate(session.ended_at)}
                  </small>
                  <small className="ph-phone-score">
                    Correct: {score}
                  </small>
                </span>

                <span className="ph-cell ph-score-column">
                  <strong className="ph-score">{score}</strong>

                  <span className="ph-bar" aria-hidden="true">
                    <span style={{ width: `${percentage}%` }} />
                  </span>
                </span>

                <span className="ph-cell ph-wide">
                  {session.host_name}
                </span>

                <span className="ph-cell ph-wide">
                  {displayDate(session.ended_at)}
                </span>

                <span className="ph-review" aria-hidden="true">
                  <span>→</span>
                </span>
              </Link>
            );
          })}

          {!items.length && (
            <div className="ui-empty">
              <h2>
                {query
                  ? "No matching quizzes"
                  : page > 0
                    ? "No more quizzes"
                    : "No completed quizzes yet"}
              </h2>

              <p>
                {query
                  ? "Try a different quiz title."
                  : "Your completed quiz reports will appear here."}
              </p>

              {!query && page === 0 && (
                <Link className="qp-button" to="/app/join">
                  Join a quiz
                </Link>
              )}
            </div>
          )}
        </>
      )}

      <nav className="ph-pagination" aria-label="Quiz history pages">
        <button
          type="button"
          disabled={page === 0 || resource.loading}
          onClick={() => setPage((value) => Math.max(0, value - 1))}
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
          onClick={() => setPage((value) => value + 1)}
        >
          Next →
        </button>
      </nav>
    </section>
  );
}
