import { useEffect, useRef } from "react";

// The "End the session now?" dialog from presenter-flow-main.html, used for
// every confirmation. Pair it with useConfirm() from ./useConfirm.js.
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
  onSettle,
}) {
  const ref = useRef(null);

  useEffect(() => {
    const dialog = ref.current;
    if (dialog && !dialog.open) dialog.showModal();
  }, []);

  return (
    <dialog
      ref={ref}
      className="qb-confirm"
      aria-labelledby="qb-confirm-title"
      onCancel={(event) => {
        event.preventDefault();
        onSettle(false);
      }}
      onClick={(event) => {
        // A click on the backdrop lands on the <dialog> itself.
        if (event.target === ref.current) onSettle(false);
      }}
    >
      <div className="qb-confirm-top">
        <span>{label}</span>
      </div>

      <div className="qb-confirm-body">
        <h2 id="qb-confirm-title">{title}</h2>
        {message && <p>{message}</p>}

        <div className="qb-confirm-actions">
          <button
            type="button"
            className="qb-btn qb-btn-paper"
            autoFocus
            onClick={() => onSettle(false)}
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            className="qb-btn"
            onClick={() => onSettle(true)}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </dialog>
  );
}
