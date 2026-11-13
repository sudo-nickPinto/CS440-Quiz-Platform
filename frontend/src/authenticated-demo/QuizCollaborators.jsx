import { useState } from "react";

import ConfirmDialog from "./ConfirmDialog";
import RequestError from "./RequestError";
import { useAction, useApi, useResource } from "./rest";
import { useConfirm } from "./useConfirm";

export default function QuizCollaborators({ quiz, embedded = false }) {
  const api = useApi();
  const action = useAction();
  const confirmer = useConfirm();
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState(null);
  const path = `/classes/${quiz.class_id}/quizzes/${quiz.quiz_id}/collaborators`;
  const resource = useResource(path);

  async function invite(event) {
    event.preventDefault();
    const normalizedEmail = email.trim().toLowerCase();
    if (!normalizedEmail) return;

    setMessage(null);
    const collaborator = await action.run(() =>
      api(path, {
        method: "POST",
        body: JSON.stringify({
          email: normalizedEmail,
          permission: "EDITOR",
        }),
      }),
    );

    if (!collaborator) return;
    setEmail("");
    setMessage({
      tone: "success",
      text: `${collaborator.display_name} can now edit this quiz.`,
    });
    resource.reload();
  }

  function inviteOnEnter(event) {
    if (event.key !== "Enter" || event.target.tagName !== "INPUT") return;
    void invite(event);
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

    setMessage(null);
    const removed = await action.run(async () => {
      await api(`${path}/${collaborator.account_id}`, { method: "DELETE" });
      return true;
    });

    if (!removed) return;
    setMessage({
      tone: "success",
      text: `${collaborator.display_name}'s access was removed.`,
    });
    resource.reload();
  }

  const InviteContainer = embedded ? "div" : "form";

  return (
    <section className="qv-collaborators" aria-labelledby="collaborators-title">
      <ConfirmDialog confirmer={confirmer} />

      <details className="qv-collaborator-disclosure">
        <summary>
          <h2 id="collaborators-title">Quiz collaborators</h2>
          <span className="qv-collaborator-count">
            {resource.loading
              ? "Loading editors…"
              : `${resource.data?.length ?? 0} ${
                  resource.data?.length === 1 ? "editor" : "editors"
                }`}
          </span>
          <span className="qv-collaborator-arrow" aria-hidden="true">
            ▾
          </span>
        </summary>

        <div className="qv-collaborator-panel">
          <p className="qv-collaborator-help">
            Invite an active member of this class by email.
          </p>

          <InviteContainer
            className="qv-collaborator-form"
            onSubmit={embedded ? undefined : invite}
            onKeyDown={embedded ? inviteOnEnter : undefined}
          >
            <label htmlFor="collaborator-email">Class member email</label>
            <div>
              <input
                id="collaborator-email"
                type="email"
                value={email}
                placeholder="student@gettysburg.edu"
                autoComplete="email"
                required
                disabled={action.busy}
                onChange={(event) => setEmail(event.target.value)}
              />
              <button
                type={embedded ? "button" : "submit"}
                className="qb-btn"
                disabled={action.busy || !email.trim()}
                onClick={embedded ? invite : undefined}
              >
                {action.busy ? "Inviting…" : "Invite editor"}
              </button>
            </div>
          </InviteContainer>

          {message && (
            <p className={`qv-share-message is-${message.tone}`} role="status">
              {message.text}
            </p>
          )}
          <RequestError error={action.error} />

          <div className="qv-collaborator-list" aria-live="polite">
            {resource.loading && <p role="status">Loading collaborators…</p>}
            <RequestError error={resource.error} retry={resource.reload} />

            {!resource.loading &&
              !resource.error &&
              resource.data?.length === 0 && (
                <p className="qv-collaborator-empty">
                  Only you can edit this quiz right now.
                </p>
              )}

            {resource.data?.map((collaborator) => (
              <article key={collaborator.account_id}>
                <span className="qv-collaborator-avatar" aria-hidden="true">
                  {collaborator.display_name.trim().charAt(0).toUpperCase() ||
                    "?"}
                </span>
                <div>
                  <strong>{collaborator.display_name}</strong>
                  <span>{collaborator.email}</span>
                </div>
                <span className="qv-collaborator-role">Editor</span>
                <button
                  type="button"
                  className="ui-linkbtn qv-remove-collaborator"
                  disabled={action.busy}
                  onClick={() => void remove(collaborator)}
                >
                  Remove
                </button>
              </article>
            ))}
          </div>
        </div>
      </details>
    </section>
  );
}
