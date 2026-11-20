import { useEffect, useId, useRef, useState } from "react";

import ConfirmDialog from "./ConfirmDialog";
import { useAction, useApi } from "./rest";
import { useConfirm } from "./useConfirm";
import SuggestionList from "../classes/SuggestionList";
import { useSuggestions } from "../classes/useSuggestions";
import { isEditorNow, withEditorChange } from "./collaboratorStatus";
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

// "+ Add collaborator" pop-up on the quiz page, laid out like "+ Add student":
// one scrolling list of the people in this class, filtered as you type. The
// quiz's collaborators come first, each with Remove; everyone else follows
// with Add.
export default function QuizCollaboratorDialog({ quiz, onClose }) {
  const ref = useRef(null);
  const api = useApi();
  const action = useAction();
  const confirmer = useConfirm();
  const path = `/classes/${quiz.class_id}/quizzes/${quiz.quiz_id}/collaborators`;
  const [text, setText] = useState("");
  const [added, setAdded] = useState(0);
  // Who was added (true) or removed (false) in this pop-up, by account id,
  // so a search result shows "Editor" or "Add" right away, before the
  // search is asked again.
  const [editorChanges, setEditorChanges] = useState({});
  // Raised after an add or remove so the search results are fetched again.
  const [searchRevision, setSearchRevision] = useState(0);
  const suggestions = useSuggestions(
    `/classes/${quiz.class_id}/quizzes/${quiz.quiz_id}/collaborator-suggestions`,
    text,
    { revision: searchRevision },
  );

  function editorsChanged(accountId, isEditor) {
    setEditorChanges((changes) => withEditorChange(changes, accountId, isEditor));
    setSearchRevision((revision) => revision + 1);
  }
  const listId = useId();
  const typedEmail = /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(text.trim());

  useEffect(() => {
    const dialog = ref.current;
    if (dialog && !dialog.open) dialog.showModal();
  }, []);

  async function addEditor(email) {
    const normalized = email.trim().toLowerCase();
    if (!normalized) return;
    const collaborator = await action.run(() =>
      api(path, {
        method: "POST",
        body: JSON.stringify({ email: normalized, permission: "EDITOR" }),
      }),
    );
    if (collaborator) {
      setAdded((count) => count + 1);
      editorsChanged(collaborator.account_id, true);
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
    // Their search result goes back to "Add", so they can be re-added.
    if (done) editorsChanged(collaborator.account_id, false);
  }


  return (
    // The class page's dialog styles live under .cl-page.
    <div className="cl-page" style={{ display: "contents" }}>
      <dialog
        ref={ref}
        className="cl-dlg cl-dlg-wide"
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
          <span id="qv-collab-title">
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

        <div className="cl-add-body">
          <form
            className="cl-add-search"
            onSubmit={(event) => {
              event.preventDefault();
              if (typedEmail) void addEditor(text);
            }}
          >
            <div className="cl-dlg-row">
              <label className="cl-search">
                <span className="cl-sr">Search this class by name or email</span>
                <input
                  type="text"
                  inputMode="email"
                  placeholder="Search this class by name or email…"
                  value={text}
                  autoFocus
                  autoComplete="off"
                  role="combobox"
                  aria-expanded={suggestions.items.length > 0}
                  aria-controls={listId}
                  aria-autocomplete="list"
                  disabled={action.busy}
                  onChange={(event) => setText(event.target.value)}
                />
              </label>
              {typedEmail && (
                <button
                  type="submit"
                  className="cl-add-one"
                  disabled={action.busy}
                >
                  + Add
                </button>
              )}
            </div>

            {action.error && (
              <p className="cl-dlg-error" role="alert">
                {action.error.message}
              </p>
            )}

            <SuggestionList
              id={listId}
              label="People in this class"
              suggestions={suggestions}
              emptyText={
                text.trim()
                  ? "No one in this class matches that search."
                  : "No one else is in this class yet."
              }
              renderPerson={(person) => {
                const editor = isEditorNow(person, editorChanges);
                return (
                  <li
                    key={person.account_id}
                    role="option"
                    aria-selected="false"
                  >
                    <span className="cl-pav" aria-hidden="true">
                      {initials(person.display_name)}
                    </span>
                    <span className="cl-pwho">
                      <strong className="cl-pname">
                        {person.display_name}
                        {editor && <span className="cl-tag is-me">Editor</span>}
                      </strong>
                      <small className="cl-pmail">{person.email}</small>
                    </span>
                    {editor ? (
                      <button
                        type="button"
                        className="cl-secondary"
                        disabled={action.busy}
                        onClick={() => void remove(person)}
                      >
                        Remove
                      </button>
                    ) : (
                      <button
                        type="button"
                        className="cl-secondary"
                        disabled={action.busy}
                        onClick={() => void addEditor(person.email)}
                      >
                        Add
                      </button>
                    )}
                  </li>
                );
              }}
            />
          </form>
        </div>

        <div className="cl-dlg-foot">
          <span aria-live="polite">
            {added === 0 ? (
              "Nobody added yet"
            ) : (
              <>
                <b>{added}</b> added
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
