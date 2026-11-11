import { useState } from "react";
import { Link } from "react-router";

import { useAccount } from "../authenticated-demo/account";
import QuizCard from "../authenticated-demo/QuizCard";
import { useResource } from "../authenticated-demo/rest";
import { useClassesResource } from "./classResources";
import { ResourceMessage } from "./ClassUI";
import {
  classesForNewQuiz,
  draftsInProgress,
  questionCountLabel,
} from "./draftHelpers";
import "./my-drafts.css";

const COLLAPSED_COUNT = 3;

// "Drafts in progress" on the Classes page: every unpublished quiz the caller
// owns or was shared on, across their classes, one click from the editor.
export function MyDrafts({ classes }) {
  const account = useAccount();
  const quizzes = useResource("/quizzes");
  const [expanded, setExpanded] = useState(false);

  const drafts = draftsInProgress(quizzes.data, classes, account.account_id);
  const canCreate = classesForNewQuiz(classes).length > 0;
  const shown = expanded ? drafts : drafts.slice(0, COLLAPSED_COUNT);

  return (
    <section className="dr-section" aria-labelledby="drafts-heading">
      <div className="dr-head">
        <h2 id="drafts-heading">
          Drafts in progress
          {!quizzes.loading && !quizzes.error && <small>{drafts.length}</small>}
        </h2>

        {canCreate && (
          <Link className="cl-button" to="/app/quizzes/new">
            + New quiz
          </Link>
        )}
      </div>

      {quizzes.loading ? (
        <p className="dr-note" role="status">
          Loading your drafts…
        </p>
      ) : quizzes.error ? (
        <div className="dr-note" role="alert">
          <p>Your drafts could not be loaded. {quizzes.error.message}</p>
          <button type="button" onClick={quizzes.reload}>
            Try again
          </button>
        </div>
      ) : drafts.length === 0 ? (
        <p className="dr-note">
          {canCreate
            ? "No drafts right now. Start one with + New quiz; quizzes shared with you show up here too."
            : "Drafts you write or that are shared with you appear here. Join a class to start one."}
        </p>
      ) : (
        <>
          <div className="qc-grid dr-grid" aria-label="Drafts in progress">
            {shown.map((draft) => (
              <QuizCard
                key={draft.quizId}
                title={draft.title}
                to={`/app/quizzes/${draft.quizId}`}
                state={{ classId: draft.classId }}
                status="Draft"
                headline={questionCountLabel(draft.questionCount)}
                linkLabel="Open quiz"
                actions={
                  !draft.classArchived && (
                    <Link
                      className="dr-edit"
                      to={`/app/quizzes/${draft.quizId}/edit`}
                      state={{ classId: draft.classId }}
                    >
                      ✎ Continue editing
                    </Link>
                  )
                }
              >
                <p>
                  <Link
                    to={`/app/classes/${draft.classId}?view=user&section=Present`}
                  >
                    {draft.className}
                  </Link>
                  {draft.classArchived && (
                    <span className="cl-tag"> Class archived</span>
                  )}
                </p>
                <p>
                  {draft.owned ? (
                    <span className="cl-tag is-me">Owned by me</span>
                  ) : (
                    <span className="cl-tag">Shared with me</span>
                  )}
                </p>
              </QuizCard>
            ))}
          </div>

          {drafts.length > COLLAPSED_COUNT && (
            <button
              type="button"
              className="dr-more"
              aria-expanded={expanded}
              onClick={() => setExpanded((value) => !value)}
            >
              {expanded ? "Show fewer" : `Show all ${drafts.length} drafts`}
            </button>
          )}
        </>
      )}
    </section>
  );
}

// /app/quizzes/new without ?class=: pick the class the quiz belongs to
// instead of sending people off to find the right "+" button.
export function NewQuizClassPicker() {
  const resource = useClassesResource();

  if (resource.status !== "ready") {
    return (
      <section className="qp-content">
        <h1>Create a quiz</h1>
        <ResourceMessage resource={resource} />
      </section>
    );
  }

  const choices = classesForNewQuiz(resource.data);

  return (
    <section
      className="qp-content dr-picker"
      aria-labelledby="new-quiz-heading"
    >
      <h1 id="new-quiz-heading">Create a quiz</h1>

      {choices.length === 0 ? (
        <>
          <p>
            Quizzes belong to a class. Join or create a class first, then come
            back here.
          </p>
          <Link className="cl-button" to="/app/classes">
            Go to my classes
          </Link>
        </>
      ) : (
        <>
          <p>Which class is this quiz for? Only that class can use it.</p>
          <ul className="dr-picker-list">
            {choices.map((item) => (
              <li key={item.id}>
                <Link to={`/app/quizzes/new?class=${item.id}`}>
                  <strong>{item.name}</strong>
                  <span>{item.roleLabel}</span>
                </Link>
              </li>
            ))}
          </ul>
          <Link to="/app/classes">← Back to classes</Link>
        </>
      )}
    </section>
  );
}
