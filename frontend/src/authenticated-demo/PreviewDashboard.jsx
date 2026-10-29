import { useState } from "react";
import { Link, Navigate, NavLink, useNavigate, useParams } from "react-router";

import { useAccount } from "./account";
import { useAction, useApi, useResource } from "./rest";
import RequestError from "./RequestError";
import ParticipantHistory from "./ParticipantHistory";
import ConfirmDialog from "./ConfirmDialog";
import { useConfirm } from "./useConfirm";

const SORTS = [
  ["recent", "Newest"],
  ["az", "A → Z"],
  ["questions", "Most questions"],
];

const plural = (count, word, many = word + "s") =>
  count === 1 ? word : many;

function displayDate(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleDateString();
}

export default function PreviewDashboard() {
  const { view } = useParams();
  const account = useAccount();
  const isAdmin = account.role === "ADMIN";
  const api = useApi();
  const navigate = useNavigate();
  const action = useAction();

  const [query, setQuery] = useState("");
  const [sort, setSort] = useState("recent");
  const [joinOpen, setJoinOpen] = useState(false);
  const [code, setCode] = useState("");
  const joinAction = useAction();
  const confirmer = useConfirm();

  const presenting = view === "present";
  const resource = useResource(presenting ? "/quizzes" : null);

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

  async function host(quiz) {
    const session = await action.run(() =>
      api(`/quizzes/${quiz.quiz_id}/sessions`, {
        method: "POST",
      }),
    );

    if (session) {
      navigate(`/app/host/${session.session_id}`);
    }
  }

  async function archive(quiz) {
    if (
      !(await confirmer.confirm({
        label: "Archive quiz",
        title: `Archive “${quiz.title}”?`,
        message: "It will no longer be available to host.",
        confirmLabel: "Archive quiz",
        cancelLabel: "Keep it",
      }))
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

  // Same request as JoinSessionPage, so joining works from the dashboard
  // strip without leaving the page.
  async function join(event) {
    event.preventDefault();

    if (!/^\d{6}$/.test(code)) return;

    const joined = await joinAction.run(() =>
      api("/sessions/join", {
        method: "POST",
        body: JSON.stringify({ join_code: code }),
      }),
    );

    if (joined) {
      navigate(`/app/play/${joined.session.session_id}`);
    }
  }

  return (
    <section className="ui-dashboard" aria-label="Dashboard">
      <ConfirmDialog confirmer={confirmer} />

      <nav className="ui-tabs" aria-label="Dashboard views">
        <Link
          className="ui-back-cell"
          to="/app/classes"
          aria-label="Back to classes"
        >
          <span aria-hidden="true">←</span>
          <span className="ui-back-word">Classes</span>
        </Link>

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

        <button
          type="button"
          className="ui-join-link"
          aria-expanded={joinOpen}
          aria-controls="dashboard-join"
          onClick={() => setJoinOpen((open) => !open)}
        >
          Join
        </button>
      </nav>

      {joinOpen && (
        <form
          className="ui-join-strip"
          id="dashboard-join"
          onSubmit={join}
        >
          <label htmlFor="dashboard-join-code">Session code</label>

          <input
            id="dashboard-join-code"
            autoFocus
            required
            inputMode="numeric"
            autoComplete="off"
            pattern="[0-9]{6}"
            maxLength={6}
            placeholder="000000"
            value={code}
            disabled={joinAction.busy}
            onChange={(event) =>
              setCode(event.target.value.replace(/\D/g, "").slice(0, 6))
            }
          />

          <button
            type="submit"
            className="qp-primary"
            disabled={code.length !== 6 || joinAction.busy}
          >
            {joinAction.busy ? "Joining…" : "Go →"}
          </button>

          <RequestError error={joinAction.error} />
        </form>
      )}

      {presenting && (
        <div className="ui-toolbar">
          <input
            type="search"
            className="ui-search"
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
            <summary>
              Filter
              {sort !== "recent" && (
                <i className="ui-filter-dot" aria-label="(sorted)" />
              )}
              <span aria-hidden="true"> ▾</span>
            </summary>

            <div className="ui-filter-panel">
              <h4>Sort by</h4>
              <div className="ui-opts" role="group" aria-label="Sort quizzes">
                {SORTS.map(([value, label]) => (
                  <button
                    type="button"
                    key={value}
                    className="ui-opt"
                    aria-pressed={sort === value}
                    onClick={() => setSort(value)}
                  >
                    {label}
                  </button>
                ))}
              </div>

              <button
                type="button"
                className="ui-linkbtn"
                disabled={resource.loading || action.busy}
                onClick={resource.reload}
              >
                Refresh list
              </button>
            </div>
          </details>

          <span className="ui-count" aria-live="polite">
            <strong>{quizzes.length}</strong>
            <span>{plural(quizzes.length, "quiz", "quizzes")}</span>
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
              <span>Qs</span>
              <span>Created</span>
              <span className="ui-sr">Actions</span>
            </div>

            {resource.loading && (
              <p className="ui-empty" role="status">
                Loading your quizzes…
              </p>
            )}

            <RequestError error={resource.error} retry={resource.reload} />

            {!resource.loading && !resource.error && !quizzes.length && (
              <div className="ui-empty">
                {query.trim() ? (
                  <p>No quizzes match “{query.trim()}”.</p>
                ) : (
                  <>
                    <p>
                      Nothing here yet. Hit <b>+</b> to make a quiz.
                    </p>
                    <Link
                      className="qp-button qp-primary"
                      to="/app/quizzes/new"
                    >
                      + New quiz
                    </Link>
                  </>
                )}
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
                    {quiz.question_count}{" "}
                    {plural(quiz.question_count, "question")}
                    {" · created "}
                    {displayDate(quiz.created_at)}
                  </small>
                </div>

                <span className="ui-desktop-cell">{quiz.question_count}</span>

                <span className="ui-desktop-cell">
                  {displayDate(quiz.created_at)}
                </span>

                {quiz.status === "PUBLISHED" ? (
                  <details className="ui-row-menu">
                    <summary aria-label={`Actions for ${quiz.title}`}>⋯</summary>

                    <div className="ui-row-options" role="menu">
                      {quiz.author_id === account.account_id && (
                        <Link
                          role="menuitem"
                          to={`/app/quizzes/${quiz.quiz_id}/edit`}
                        >
                          <span aria-hidden="true">✎</span> Edit
                        </Link>
                      )}

                      {quiz.author_id === account.account_id && (
                        <button
                          type="button"
                          role="menuitem"
                          disabled={action.busy}
                          onClick={() => void host(quiz)}
                        >
                          <span aria-hidden="true">▶</span> Host live session
                        </button>
                      )}

                      <button
                        type="button"
                        role="menuitem"
                        className="ui-danger"
                        disabled={action.busy}
                        onClick={() => void archive(quiz)}
                      >
                        <span aria-hidden="true">▣</span> Archive
                      </button>
                    </div>
                  </details>
                ) : (
                  <span className="ui-row-menu" aria-hidden="true" />
                )}
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
