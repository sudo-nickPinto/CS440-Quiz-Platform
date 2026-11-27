import { useEffect, useId, useRef, useState } from "react";

import RequestError from "../authenticated-demo/RequestError";
import { useAction, useApi } from "../authenticated-demo/rest";

const COMMENT_LIMIT = 1000;

export default function RejectSubmissionDialog({ classId, submissionId, onClose, onRejected }) {
  const dialogRef = useRef(null);
  const titleId = useId();
  const commentId = useId();
  const helpId = useId();
  const [comment, setComment] = useState("");
  const action = useAction();
  const api = useApi();
  const trimmed = comment.trim();
  const length = Array.from(trimmed).length;
  const tooLong = length > COMMENT_LIMIT;

  useEffect(() => {
    const dialog = dialogRef.current;
    const trigger = document.activeElement;
    dialog.showModal();
    return () => {
      dialog.close();
      if (trigger instanceof HTMLElement && trigger.isConnected) trigger.focus();
    };
  }, []);

  async function reject(event) {
    event.preventDefault();
    if (tooLong) return;
    const saved = await action.run(async () => {
      await api(`/classes/${classId}/quiz-submissions/${submissionId}`, {
        method: "PATCH",
        body: JSON.stringify({
          status: "REJECTED",
          ...(trimmed && { rejection_comment: trimmed }),
        }),
      });
      return true;
    });
    if (saved) {
      onClose();
      onRejected();
    }
  }

  return (
    <dialog
      ref={dialogRef}
      className="qb-confirm cl-reject-dialog"
      aria-labelledby={titleId}
      aria-busy={action.busy || undefined}
      onCancel={(event) => {
        event.preventDefault();
        if (!action.busy) onClose();
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget && !action.busy) onClose();
      }}
    >
      <div className="qb-confirm-top">Approval decision</div>
      <form className="qb-confirm-body" onSubmit={(event) => void reject(event)}>
        <h2 id={titleId}>Reject submission</h2>
        <label htmlFor={commentId}>Rejection comment (optional)</label>
        <textarea
          id={commentId}
          value={comment}
          onChange={(event) => setComment(event.target.value)}
          rows={4}
          aria-describedby={helpId}
          aria-invalid={tooLong || undefined}
          disabled={action.busy}
          autoFocus
        />
        <p id={helpId}>
          {tooLong
            ? "Shorten the comment to 1,000 characters or fewer."
            : `${length.toLocaleString()} / 1,000 characters`}
        </p>
        <RequestError error={action.error} />
        <div className="qb-confirm-actions">
          <button type="button" className="qb-btn qb-btn-paper" onClick={onClose} disabled={action.busy}>
            Cancel
          </button>
          <button type="submit" className="qb-btn" disabled={action.busy || tooLong}>
            {action.busy ? "Rejecting…" : "Reject submission"}
          </button>
        </div>
      </form>
    </dialog>
  );
}
