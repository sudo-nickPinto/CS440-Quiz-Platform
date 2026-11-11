import { useState } from "react";
import { useResource } from "../authenticated-demo/rest";
import RequestError from "../authenticated-demo/RequestError";

function date(value) {
  return value ? new Date(value).toLocaleString() : "—";
}

export default function SubmissionCard({
  submission,
  classInfo,
  accountId,
  busy,
  onDecide,
  onWithdraw,
}) {
  const [opened, setOpened] = useState(false);

  const preview = useResource(
    opened
      ? `/classes/${classInfo.id}/quiz-submissions/${submission.submission_id}/preview`
      : null,
  );

  const data = preview.data;
  const version = data?.version;
  const record = data?.submission ?? submission;
  const pending = record.status === "PENDING";

  return (
    <article
      className="qw-card"
      aria-label={`Submission ${submission.submission_id}`}
    >
      <span className="qw-badge">{record.status}</span>

      <h2>{version?.title ?? `Version ID ${submission.quiz_version_id}`}</h2>

      <p>Submission #{submission.submission_id}</p>
      <p>Version ID: {submission.quiz_version_id}</p>

      <p>
        Submitted by{" "}
        {data?.submitted_by_name ?? `account #${submission.submitted_by_id}`}
      </p>

      <p>Submitted: {date(record.submitted_at)}</p>

      {record.decided_at && (
        <p>
          Decision: {date(record.decided_at)} · Account #{record.decided_by_id}
        </p>
      )}

      {!opened && (
        <button type="button" onClick={() => setOpened(true)}>
          Review submitted version
        </button>
      )}

      {preview.loading && <p role="status">Loading submitted version…</p>}

      <RequestError error={preview.error} retry={preview.reload} />

      {version && (
        <section className="qw-preview" aria-label="Submitted version preview">
          <h3>Submitted version {version.version_number}</h3>

          {version.description && <p>{version.description}</p>}

          <ol>
            {[...version.questions]
              .sort((a, b) => a.question_order - b.question_order)
              .map((question) => (
                <li key={question.question_id}>
                  <strong>{question.question_text}</strong>

                  <ul>
                    {[...question.choices]
                      .sort((a, b) => a.choice_order - b.choice_order)
                      .map((choice) => (
                        <li key={choice.choice_id}>
                          {choice.choice_text}
                          {choice.is_correct && " — Correct"}
                        </li>
                      ))}
                  </ul>

                  <p>
                    {question.time_limit_seconds} seconds ·{" "}
                    {question.base_points} points
                  </p>

                  {question.explanation && <p>{question.explanation}</p>}
                </li>
              ))}
          </ol>

          {classInfo.canManage && data.approval_block_reason && (
            <p role="status">{data.approval_block_reason}</p>
          )}
        </section>
      )}

      {!opened && pending && classInfo.canManage && (
        <p>Load the submitted version before approving it.</p>
      )}

      <div className="qw-actions">
        {pending && classInfo.canManage && (
          <>
            <button
              type="button"
              disabled={
                busy ||
                classInfo.archived ||
                preview.loading ||
                Boolean(preview.error) ||
                !data?.can_approve
              }
              onClick={() => onDecide(submission, "APPROVED")}
            >
              Approve
            </button>

            <button
              type="button"
              disabled={busy}
              onClick={() => onDecide(submission, "REJECTED")}
            >
              Reject
            </button>
          </>
        )}

        {pending && submission.submitted_by_id === accountId && (
          <button
            type="button"
            disabled={busy}
            onClick={() => onWithdraw(submission)}
          >
            Withdraw
          </button>
        )}
      </div>
    </article>
  );
}
