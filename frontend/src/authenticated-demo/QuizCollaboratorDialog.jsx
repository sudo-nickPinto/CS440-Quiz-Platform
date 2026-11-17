import { useEffect, useRef, useState } from "react";

import ConfirmDialog from "./ConfirmDialog";
import { useAction, useApi, useResource } from "./rest";
import { useConfirm } from "./useConfirm";
import "../classes/class-admin.css";

function initials(name) {
  const parts = String(name ?? "").trim().split(/\s+/).filter(Boolean);
  return (parts[0]?.[0] ?? "?").toUpperCase() + (parts[1]?.[0] ?? "").toUpperCase();
}

// The right cell of the quiz page and editor header: one big navy button
// that opens QuizCollaboratorDialog.
export function AddCollaboratorCell({ onOpen }) {
  return (
    <div className="qe-state qv-share-cell">
      <button type="button" className="qv-share" onClick={onOpen}>
        <svg
          className="qv-share-icon"
          viewBox="0 0 24 24"
          aria-hidden="true"
          focusable="false"
        >
          <circle cx="9" cy="8" r="4" />
          <path d="M2 21c0-4 3-6.5 7-6.5s7 2.5 7 6.5" />
          <path d="M19 7v6M16 10h6" />
        </svg>
        Add collaborator
      </button>
    </div>
  );
}

// "+ Add collaborator" pop-up on the quiz page: invite a class member by
// email to edit the quiz, and see or remove the current editors. Same look
// as the class page's "+ Add member" pop-up (AddMemberDialog).
export default function QuizCollaboratorDialog({ quiz, onClose }) {
  const ref = useRef(null);
  const api = useApi();
  const action = useAction();
  const confirmer = useConfirm();
  const path = `/classes/${quiz.class_id}/quizzes/${quiz.quiz_id}/collaborators`;
  const people = useResource(path);
  const [email, setEmail] = useState("");
  const [added, setAdded] = useState(0);

  useEffect(() => {
    const dialog = ref.current;
    if (dialog && !dialog.open) dialog.showModal();
  }, []);

  async function invite(event) {
    event.preventDefault();
    const normalized = email.trim().toLowerCase();
    if (!normalized) return;
    const collaborator = await action.run(() =>
      api(path, {
        method: "POST",
        body: JSON.stringify({ email: normalized, permission: "EDITOR" }),
      }),
    );
    if (collaborator) {
      setEmail("");
      setAdded((count) => count + 1);
      people.reload();
    }
  }

  async function remove(collaborator) {
    const confirmed = await confirmer.confirm({
      label: "Remove collaborator",
      title: `Remove ${collaborator.display_name}?`,
      message:
        "They will lose access to this quiz immediately. Their previous edits remain saved.",
      confirmLabel: "Remove access",
      cancelLabel: "Keep collaborator",
    });
    if (!confirmed) return;
    const done = await action.run(async () => {
      await api(`${path}/${collaborator.account_id}`, { method: "DELETE" });
      return true;
    });
    if (done) people.reload();
  }

  const editors = Array.isArray(people.data) ? people.data : [];

  return (
    // The class page's dialog styles live under .cl-page.
    <div className="cl-page" style={{ display: "contents" }}>
      <dialog
        ref={ref}
        className="cl-dlg"
        aria-labelledby="qv-collab-title"
        onCancel={(event) => {
          event.preventDefault();
          onClose();
        }}
        onClick={(event) => {
          // A click on the backdrop lands on the <dialog> itself.
          if (event.target === ref.current) onClose();
        }}
      >
        <div className="cl-dlg-top">
          <span>
            Add collaborator · <b>{quiz.version.title}</b>
          </span>
          <button
            type="button"
            className="cl-dlg-x"
            aria-label="Close"
            onClick={onClose}
          >
            ×
          </button>
        </div>

        <form className="cl-dlg-head" onSubmit={invite}>
          <h2 id="qv-collab-title">Who else can edit this quiz?</h2>
          <div className="cl-dlg-row">
            <label className="cl-search">
              <span className="cl-sr">Email of someone in this class</span>
              <input
                type="email"
                placeholder="Email of someone in this class…"
                value={email}
                autoFocus
                required
                autoComplete="email"
                disabled={action.busy}
                onChange={(event) => setEmail(event.target.value)}
              />
            </label>
            <button
              type="submit"
              className="cl-add-one"
              disabled={action.busy || !email.trim()}
            >
              + Invite
            </button>
          </div>
          <p>
            They need to be a student or organizer in this class. Editors can change
            the questions and answers.
          </p>
          {action.error && (
            <p className="cl-dlg-error" role="alert">
              {action.error.message}
            </p>
          )}
        </form>

        <div className="cl-dlg-sub">
          <span>Editors</span>
          <span>
            {editors.length} {editors.length === 1 ? "person" : "people"}
          </span>
        </div>

        <div className="cl-people" aria-live="polite">
          {people.loading ? (
            <p className="cl-dlg-empty" role="status">
              Loading collaborators…
            </p>
          ) : people.error ? (
            <p className="cl-dlg-empty" role="alert">
              {people.error.message}{" "}
              <button type="button" onClick={people.reload}>
                Retry
              </button>
            </p>
          ) : editors.length === 0 ? (
            <p className="cl-dlg-empty">Only you can edit this quiz right now.</p>
          ) : (
            editors.map((person) => (
              <div className="cl-person" key={person.account_id}>
                <span className="cl-pav" aria-hidden="true">
                  {initials(person.display_name)}
                </span>
                <span>
                  <strong className="cl-pname">{person.display_name}</strong>
                  <small className="cl-pmail">{person.email}</small>
                </span>
                <button
                  type="button"
                  className="cl-secondary"
                  disabled={action.busy}
                  onClick={() => void remove(person)}
                >
                  Remove
                </button>
              </div>
            ))
          )}
        </div>

        <div className="cl-dlg-foot">
          <span aria-live="polite">
            {added === 0 ? (
              "Nobody invited yet"
            ) : (
              <>
                <b>{added}</b> invited
              </>
            )}
          </span>
          <button type="button" className="cl-add-one" onClick={onClose}>
            Done
          </button>
        </div>

        <ConfirmDialog confirmer={confirmer} />
      </dialog>
    </div>
  );
}
