import { useEffect, useId, useRef } from "react";

// The "End the session now?" dialog from presenter-flow-main.html, used for
// every confirmation. Pair it with useConfirm() from ./useConfirm.js.
// Optional request fields for dialogs that act before closing (the live-quiz
// popup): `details`, extra content under the message (say an error), and
// `busy`, which disables both buttons and ignores Escape and the backdrop,
// and `className`, an extra class on the <dialog> for a restyled variant.
export default function ConfirmDialog({ confirmer }) {
  if (!confirmer.request) return null;

  return <Dialog {...confirmer.request} onSettle={confirmer.settle} />;
}

function Dialog({
  label = "Please confirm",
  title,
  message,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  details = null,
  busy = false,
  className = "",
  onSettle,
}) {
  const ref = useRef(null);
  const titleId = useId();

  useEffect(() => {
    const dialog = ref.current;
    if (dialog && !dialog.open) dialog.showModal();
  }, []);

  return (
    <dialog
      ref={ref}
      className={className ? `qb-confirm ${className}` : "qb-confirm"}
      aria-labelledby={titleId}
      aria-busy={busy || undefined}
      onCancel={(event) => {
        event.preventDefault();
        if (!busy) onSettle(false);
      }}
      onClick={(event) => {
        // A click on the backdrop lands on the <dialog> itself.
        if (event.target === ref.current && !busy) onSettle(false);
      }}
    >
      <div className="qb-confirm-top">
        <span>{label}</span>
      </div>

      <div className="qb-confirm-body">
        <h2 id={titleId}>{title}</h2>
        {message && <p>{message}</p>}
        {details}

        <div className="qb-confirm-actions">
          <button
            type="button"
            className="qb-btn qb-btn-paper"
            autoFocus
            disabled={busy}
            onClick={() => onSettle(false)}
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            className="qb-btn"
            disabled={busy}
            onClick={() => onSettle(true)}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </dialog>
  );
}
