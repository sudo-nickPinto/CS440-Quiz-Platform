import QuizCard from "./QuizCard";
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
          className="ui-search"
          aria-label="Search quizzes taken"
          placeholder="Search quizzes…"
          maxLength={200}
          value={query}
          onChange={(event) => changeQuery(event.target.value)}
        />

        <details className="ui-filter">
          <summary>
            Filter
            {sort !== "recent" && (
              <i className="ui-filter-dot" aria-label="(sorted)" />
            )}
            <span aria-hidden="true"> ▾</span>
          </summary>

          <div className="ui-filter-panel">
            <h4>Sort by</h4>
            <div className="ui-opts" role="group" aria-label="Sort quizzes taken">
              {[
                ["recent", "Most recent"],
                ["score", "Best score"],
                ["az", "A → Z"],
              ].map(([value, label]) => (
                <button
                  type="button"
                  key={value}
                  className="ui-opt"
                  aria-pressed={sort === value}
                  onClick={() => changeSort(value)}
                >
                  {label}
                </button>
              ))}
            </div>

            <button
              type="button"
              className="ui-linkbtn"
              disabled={resource.loading}
              onClick={resource.reload}
            >
              Refresh list
            </button>
          </div>
        </details>

        <span className="ui-count" aria-live="polite">
          <strong>{resource.loading ? "…" : items.length}</strong>
          <span>taken</span>
        </span>
      </div>

      {resource.loading && (
        <p className="ui-empty" role="status">
          Loading your quizzes…
        </p>
      )}

      <RequestError error={resource.error} retry={resource.reload} />

      {!resource.loading && !resource.error && (
        <>
          {items.length > 0 && <div className="qc-grid" aria-label="Completed quizzes">
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
              <QuizCard
                key={session.session_id}
                title={session.quiz_title}
                to={"/app/results/me/" + session.session_id}
                status="Completed"
                headline={session.rank == null ? "Rank unavailable" : "Rank #" + session.rank + " of " + session.total_participants}
                linkLabel="View report"
              >
                <p>Session #{session.session_id} · {displayDate(session.ended_at)}</p>
                <p>Hosted by {session.host_name}</p>
                <p><strong>Correct: {score}</strong></p>
                <span className="qc-progress" aria-hidden="true">
                  <span style={{ width: percentage + "%" }} />
                </span>
              </QuizCard>
            );
          })}
          </div>}

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
