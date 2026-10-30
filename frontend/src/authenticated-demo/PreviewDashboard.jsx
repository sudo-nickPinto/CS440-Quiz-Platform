import { useState } from "react";
import { Link, Navigate, NavLink, useParams } from "react-router";

import { useClassesResource } from "../classes/classResources";
import { useAccount } from "./account";
import HostQuizButton from "./HostQuizButton";
import { useAction, useApi, useResource } from "./rest";
import RequestError from "./RequestError";
import ParticipantHistory from "./ParticipantHistory";

function displayDate(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleDateString();
}

export default function PreviewDashboard() {
  const { view } = useParams();
  const account = useAccount();
  const isAdmin = account.role === "ADMIN";
  const api = useApi();
  const action = useAction();

  const [query, setQuery] = useState("");
  const [sort, setSort] = useState("recent");

  const presenting = view === "present";
  const resource = useResource(presenting ? "/quizzes" : null);
  const classes = useClassesResource();
  const hostClasses =
    classes.status === "ready"
      ? classes.data.filter((item) => item.canManage && !item.archived)
      : [];

  if (view === "taken") {
    return <Navigate to="/app/dashboard/participate" replace />;
  }

  if (!["present", "participate"].includes(view)) {
    return <Navigate to="/app/dashboard/present" replace />;
  }

  const quizzes = (resource.data || [])
    .filter(
      (quiz) =>
        (isAdmin || quiz.author_id === account.account_id) &&
        ["PUBLISHED", "ARCHIVED"].includes(quiz.status) &&
        quiz.title.toLowerCase().includes(query.trim().toLowerCase()),
    )
    .sort((a, b) => {
      if (sort === "az") {
        return a.title.localeCompare(b.title);
      }

      if (sort === "questions") {
        return b.question_count - a.question_count;
      }

      return (
        (Date.parse(b.created_at) || 0) - (Date.parse(a.created_at) || 0) ||
        b.quiz_id - a.quiz_id
      );
    });

  async function archive(quiz) {
    if (
      !window.confirm(
        `Archive "${quiz.title}"? It will no longer be available to host.`,
      )
    ) {
      return;
    }

    await action.run(async () => {
      await api(`/quizzes/${quiz.quiz_id}/archive`, {
        method: "PATCH",
      });
      resource.reload();
    });
  }

  return (
    <section className="ui-dashboard" aria-label="Dashboard">
      <nav className="ui-tabs" aria-label="Dashboard views">
        <NavLink to="/app/dashboard/present">Present</NavLink>

        <NavLink to="/app/dashboard/participate">Participate</NavLink>

        <Link
          className="ui-create"
          to="/app/quizzes/new"
          aria-label="Create a quiz"
          title="Create a quiz"
        >
          +
        </Link>

        <Link className="ui-join-link" to="/app/join">
          Join
        </Link>
      </nav>

      {presenting && (
        <div className="ui-toolbar">
          <input
            type="search"
            aria-label={
              isAdmin
                ? "Search published and archived quizzes"
                : "Search your published and archived quizzes"
            }
            placeholder={
              isAdmin ? "Search all quizzes…" : "Search your quizzes…"
            }
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />

          <details className="ui-filter">
            <summary>Filter{sort !== "recent" ? " •" : ""}</summary>

            <div className="ui-filter-panel">
              <label>
                Sort quizzes
                <select
                  value={sort}
                  onChange={(event) => setSort(event.target.value)}
                >
                  <option value="recent">Newest first</option>
                  <option value="az">Title A–Z</option>
                  <option value="questions">Most questions</option>
                </select>
              </label>

              <p>
                {isAdmin
                  ? "Showing all published and archived quizzes."
                  : "Showing your published and archived quizzes."}
              </p>

              <button
                type="button"
                disabled={resource.loading || action.busy}
                onClick={resource.reload}
              >
                Refresh list
              </button>
            </div>
          </details>

          <span className="ui-count" aria-live="polite">
            <strong>{quizzes.length}</strong>
            <span>quizzes</span>
          </span>
        </div>
      )}

      <div className="ui-dashboard-list">
        <RequestError error={action.error} />

        {action.busy && (
          <p className="ui-message" role="status">
            Saving your request…
          </p>
        )}

        {presenting ? (
          <>
            <div className="ui-list-heading" aria-hidden="true">
              <span>Status</span>
              <span>Quiz</span>
              <span>Questions</span>
              <span>Created</span>
              <span>Actions</span>
            </div>

            {resource.loading && (
              <p className="ui-empty" role="status">
                Loading your quizzes…
              </p>
            )}

            <RequestError error={resource.error} retry={resource.reload} />

            {!resource.loading && !resource.error && !quizzes.length && (
              <div className="ui-empty">
                <h1>No matching quizzes</h1>
                <p>Create and publish a quiz to start hosting.</p>
                <Link className="qp-button" to="/app/quizzes/new">
                  Create a quiz
                </Link>
              </div>
            )}

            {quizzes.map((quiz) => (
              <article className="ui-quiz-row" key={quiz.quiz_id}>
                <span
                  className={
                    quiz.status === "ARCHIVED"
                      ? "ui-published ui-archived"
                      : "ui-published"
                  }
                >
                  {quiz.status === "ARCHIVED" ? "Archived" : "Published"}
                </span>

                <div className="ui-quiz-title">
                  <Link to={`/app/quizzes/${quiz.quiz_id}`}>{quiz.title}</Link>

                  <small>
                    {quiz.status === "ARCHIVED" ? "Archived" : "Published"}
                    {" · "}
                    {quiz.question_count} questions
                  </small>
                </div>

                <span className="ui-desktop-cell">{quiz.question_count}</span>

                <span className="ui-desktop-cell">
                  {displayDate(quiz.created_at)}
                </span>

                <details className="ui-row-menu">
                  <summary aria-label={`Actions for ${quiz.title}`}>⋯</summary>

                  <div className="ui-row-options">
                    <Link to={`/app/quizzes/${quiz.quiz_id}`}>View quiz</Link>
                    {(quiz.author_id === account.account_id || isAdmin) && (
                      <Link to={`/app/quizzes/${quiz.quiz_id}/reports`}>
                        Report
                      </Link>
                    )}

                    {quiz.author_id === account.account_id &&
                      quiz.status === "PUBLISHED" && (
                        <Link to={`/app/quizzes/${quiz.quiz_id}/edit`}>
                          Edit quiz
                        </Link>
                      )}

                    {quiz.author_id === account.account_id &&
                      quiz.status === "PUBLISHED" && (
                        <HostQuizButton
                          quiz={quiz}
                          action={action}
                          hostClasses={hostClasses}
                          hostClassesStatus={classes.status}
                          hostClassesError={classes.error}
                          reloadHostClasses={classes.reload}
                        />
                      )}

                    {quiz.status === "PUBLISHED" && (
                      <button
                        type="button"
                        disabled={action.busy}
                        onClick={() => void archive(quiz)}
                      >
                        Archive quiz
                      </button>
                    )}
                  </div>
                </details>
              </article>
            ))}
          </>
        ) : (
          <ParticipantHistory />
        )}
      </div>
    </section>
  );
}
