import { useState } from "react";
import { Link } from "react-router";

import { useAccount } from "../authenticated-demo/account";
import ConfirmDialog from "../authenticated-demo/ConfirmDialog";
import RequestError from "../authenticated-demo/RequestError";
import { useAction, useApi, useResource } from "../authenticated-demo/rest";
import { useConfirm } from "../authenticated-demo/useConfirm";
import {
  grantedLabel,
  historySentence,
  historyTime,
  isFaculty,
  looksLikeEmail,
  orderFaculty,
} from "./facultyAccess";
import "./faculty-access.css";

// Account menu → Faculty access (issue #116): faculty give other faculty the
// ability to create classes, or take it away, without a database change.
export default function FacultyAccessPage() {
  const account = useAccount();

  if (!isFaculty(account)) {
    return (
      <section>
        <div className="ui-titlebar">
          <span>Faculty access</span>
          <span>Account</span>
        </div>
        <div className="fa-page">
          <h1>Faculty only</h1>
          <p>Only faculty can manage faculty access.</p>
          <Link className="qp-button" to="/app/classes">
            Back to classes
          </Link>
        </div>
      </section>
    );
  }

  return <FacultyAccess />;
}

function FacultyAccess() {
  const api = useApi();
  const resource = useResource("/faculty");
  const action = useAction();
  const confirmer = useConfirm();
  const [email, setEmail] = useState("");
  const [formError, setFormError] = useState("");
  const [notice, setNotice] = useState("");

  const busy = action.busy || resource.refreshing;

  async function grant(event) {
    event.preventDefault();
    const wanted = email.trim();
    setNotice("");
    if (!looksLikeEmail(wanted)) {
      setFormError("Enter a full email address, like name@gettysburg.edu.");
      return;
    }
    setFormError("");

    const sure = await confirmer.confirm({
      label: "Give faculty access",
      title: `Give faculty access to ${wanted}?`,
      message:
        "They'll be able to create classes, and organizers can make them an organizer of a class. Only do this for approved faculty.",
      confirmLabel: "Give access",
      cancelLabel: "Cancel",
    });
    if (!sure) return;

    const added = await action.run(() =>
      api("/faculty", {
        method: "POST",
        body: JSON.stringify({ email: wanted }),
      }),
    );
    if (!added) return;
    setEmail("");
    setNotice(`${added.display_name} now has faculty access.`);
    resource.refresh();
  }

  async function revoke(member) {
    setNotice("");
    const sure = await confirmer.confirm({
      label: "Remove faculty access",
      title: `Remove faculty access from ${member.display_name}?`,
      message:
        "They keep their account and their classes, but can't create classes or act as an organizer until someone gives faculty access back.",
      confirmLabel: "Remove access",
      cancelLabel: "Keep access",
    });
    if (!sure) return;

    const done = await action.run(async () => {
      await api(`/faculty/${member.account_id}`, { method: "DELETE" });
      return true;
    });
    if (!done) return;
    setNotice(`${member.display_name} no longer has faculty access.`);
    resource.refresh();
  }

  const data = resource.data;
  const faculty = orderFaculty(data?.faculty);
  const history = data?.history ?? [];

  return (
    <section>
      <ConfirmDialog confirmer={confirmer} />

      <div className="ui-titlebar">
        <span>Faculty access</span>
        <span>Account</span>
      </div>

      <div className="fa-page">
        <p className="ui-eyebrow">Account</p>
        <h1>
          Manage <span className="ui-highlight">faculty access</span>
        </h1>
        <p className="fa-lede">
          Faculty can create classes and can be made organizers. Faculty access
          doesn&apos;t open anyone&apos;s classes: people still only see the
          classes they belong to.
        </p>

        <form className="fa-card fa-add" onSubmit={grant} noValidate>
          <h2>Add faculty</h2>
          <label htmlFor="fa-email">Their email address</label>
          <div className="fa-add-row">
            <input
              id="fa-email"
              type="email"
              autoComplete="off"
              spellCheck={false}
              placeholder="name@gettysburg.edu"
              value={email}
              maxLength={320}
              aria-invalid={formError ? true : undefined}
              aria-describedby="fa-email-help"
              disabled={busy}
              onChange={(event) => {
                setEmail(event.target.value);
                setFormError("");
              }}
            />
            <button
              type="submit"
              className="qp-button qp-primary"
              disabled={busy || !email.trim()}
            >
              {action.busy ? "Saving…" : "Give faculty access"}
            </button>
          </div>
          <p id="fa-email-help" className="fa-help">
            They need to sign in to QuizBurg once first, so their account
            exists.
          </p>
          {formError && (
            <p className="fa-error" role="alert">
              {formError}
            </p>
          )}
        </form>

        <RequestError error={action.error} />
        {notice && (
          <p className="fa-notice" role="status">
            {notice}
          </p>
        )}

        <section className="fa-card" aria-labelledby="fa-list-title">
          <h2 id="fa-list-title">
            Current faculty
            {data && <small>{faculty.length}</small>}
          </h2>

          {resource.loading ? (
            <p role="status">Loading faculty…</p>
          ) : resource.error ? (
            <RequestError error={resource.error} retry={resource.reload} />
          ) : (
            <ul className="fa-list">
              {faculty.map((member) => (
                <li key={member.account_id}>
                  <div className="fa-person">
                    <strong>
                      {member.display_name}
                      {member.is_me && <span className="fa-tag">You</span>}
                    </strong>
                    <span className="fa-email">{member.email}</span>
                    <small>{grantedLabel(member)}</small>
                  </div>
                  {!member.is_me && (
                    <button
                      type="button"
                      className="qp-button fa-remove"
                      disabled={busy}
                      onClick={() => void revoke(member)}
                    >
                      Remove access
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>

        {data && (
          <section className="fa-card" aria-labelledby="fa-history-title">
            <h2 id="fa-history-title">Recent changes</h2>
            {history.length === 0 ? (
              <p className="fa-help">
                Nothing yet. Every grant and removal made on this page shows
                up here.
              </p>
            ) : (
              <ol className="fa-history">
                {history.map((item) => (
                  <li key={item.event_id}>
                    <span
                      className={`fa-action is-${item.action.toLowerCase()}`}
                    >
                      {item.action === "REVOKED" ? "Removed" : "Added"}
                    </span>
                    <span>
                      {historySentence(item)}
                      <small>{historyTime(item)}</small>
                    </span>
                  </li>
                ))}
              </ol>
            )}
          </section>
        )}

        <Link className="qp-button" to="/app/classes">
          Back to classes
        </Link>
      </div>
    </section>
  );
}
