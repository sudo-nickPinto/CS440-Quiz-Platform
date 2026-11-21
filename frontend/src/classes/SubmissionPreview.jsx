import { useState } from "react";
import { Link, useParams } from "react-router";

import { useAction, useApi, useResource } from "../authenticated-demo/rest";
import RequestError from "../authenticated-demo/RequestError";
import { canEditQuiz } from "../authenticated-demo/quizEditing";
import {
  useNotifications,
  useNotificationsReconnect,
} from "../authenticated-demo/notifications";
import { approvalLabel, submissionPreviewPath } from "./classHelpers";
import { useClassResource } from "./classResources";
import RejectSubmissionDialog from "./RejectSubmissionDialog";

// Read-only view of exactly the version a member submitted for approval.
// The quiz page shows the newest (possibly draft) version, so organizers
// review here instead, and can decide from this page.
export default function SubmissionPreviewPage() {
  const { classId, submissionId } = useParams();
  const path = submissionPreviewPath(classId, submissionId);
  const preview = useResource(path);
  const { refresh } = preview;
  const quizId = preview.data?.submission?.quiz_id;
  const quiz = useResource(Number.isSafeInteger(quizId) && quizId > 0 ? `/quizzes/${quizId}` : null);
  const canEdit = quiz.data && canEditQuiz(quiz.data);

  // Another organizer deciding, or the member withdrawing, updates the
  // status here without a reload.
  useNotifications("submission_changed", (event) => {
    if (path && Number(event?.submission_id) === Number(submissionId)) refresh();
  });
  useNotificationsReconnect(() => {
    if (path) refresh();
  });
  const classInfo = useClassResource(classId);
  const api = useApi();
  const action = useAction();
  const [rejecting, setRejecting] = useState(false);
  const organizer = classInfo.status === "ready" && classInfo.data.canManage;
  const backTo = organizer
    ? `/app/classes/${classId}?section=Approvals`
    : `/app/classes/${classId}?view=user&section=My%20quizzes`;

  async function decide(status) {
    const done = await action.run(async () => {
      await api(`/classes/${classId}/quiz-submissions/${submissionId}`, {
        method: "PATCH",
        body: JSON.stringify({ status }),
      });
      return true;
    });
    if (done) preview.reload();
  }

  return (
    <section className="cl-page">
      <header className="cl-classbar">
        <Link className="cl-button cl-secondary" to={backTo}>
          ← {organizer ? "Approvals" : "My quizzes"}
        </Link>
        <div className="cl-class-title">
          <p className="cl-eyebrow">Submitted version</p>
          <h1>{preview.data ? preview.data.version.title : "Submission"}</h1>
        </div>
        {canEdit && (
          <Link className="cl-button" to={`/app/quizzes/${quizId}/edit`}>
            Edit quiz
          </Link>
        )}
      </header>

      {!path ? (
        <div className="cl-state" role="alert">
          <h2>Invalid address</h2>
          <p>Open this submission from the class page.</p>
        </div>
      ) : preview.loading ? (
        <div className="cl-state" role="status">
          <h2>Loading submission…</h2>
        </div>
      ) : preview.error ? (
        <div className="cl-state">
          <RequestError error={preview.error} retry={preview.reload} />
        </div>
      ) : preview.data ? (
        <SubmissionBody
          data={preview.data}
          organizer={organizer}
          action={action}
          archived={classInfo.status === "ready" && classInfo.data.archived}
          onDecide={(status) => void decide(status)}
          onReject={() => setRejecting(true)}
        />
      ) : null}
      {rejecting && (
        <RejectSubmissionDialog
          classId={classId}
          submissionId={submissionId}
          onClose={() => setRejecting(false)}
          onRejected={preview.reload}
        />
      )}
    </section>
  );
}

function SubmissionBody({ data, organizer, action, archived, onDecide, onReject }) {
  const { submission, version } = data;
  const decided = submission.decided_by_name
    ? ` by ${submission.decided_by_name}`
    : "";
  const pending = submission.status === "PENDING";

  return (
    <>
      <section className="cl-summary" aria-label="Submission details">
        <div className="cl-stat">
          <span>Version</span>
          <strong>
            v{version.version_number}
            {submission.is_current_version ? "" : " · outdated"}
          </strong>
        </div>
        <div className="cl-stat">
          <span>Submitted by</span>
          <strong>{submission.submitter_name}</strong>
        </div>
        <div className="cl-stat">
          <span>Status</span>
          <strong>
            {approvalLabel(submission.status)}
            {pending ? "" : decided}
          </strong>
        </div>
        <div className="cl-stat">
          <span>Questions</span>
          <strong>{version.questions.length}</strong>
        </div>
      </section>

      <RequestError error={action.error} />

      {organizer && pending && (
        <div className="cl-approval cl-preview-actions">
          <button
            type="button"
            className="cl-decide is-approve"
            disabled={action.busy || archived || !submission.is_current_version}
            title={
              submission.is_current_version
                ? undefined
                : "A newer version of this quiz exists; only rejection is possible."
            }
            onClick={() => onDecide("APPROVED")}
          >
            Approve this version
          </button>
          <button
            type="button"
            className="cl-decide"
            disabled={action.busy}
            onClick={onReject}
          >
            Reject
          </button>
        </div>
      )}

      {version.description && <p className="cl-section-note">{version.description}</p>}

      <ol className="cl-preview-questions">
        {version.questions.map((question) => (
          <li key={question.question_id}>
            <p className="cl-preview-q">{question.question_text}</p>
            <ul aria-label="Choices">
              {question.choices.map((choice) => (
                <li
                  key={choice.choice_id}
                  className={choice.is_correct ? "is-correct" : undefined}
                >
                  {choice.choice_text}
                  {choice.is_correct && <strong> — correct</strong>}
                </li>
              ))}
            </ul>
            <p className="cl-preview-meta">
              {question.time_limit_seconds}s · {question.base_points} points
            </p>
            {question.explanation && (
              <p className="cl-preview-meta">Why: {question.explanation}</p>
            )}
          </li>
        ))}
      </ol>
    </>
  );
}
