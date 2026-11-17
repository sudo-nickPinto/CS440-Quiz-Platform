import { useEffect, useId, useRef, useState } from "react";

import RequestError from "../authenticated-demo/RequestError";
import { useAction, useApi, useResource } from "../authenticated-demo/rest";
import { initials } from "./classHelpers";
import { ReportTable } from "./ReportTable";
import {
  outcomeLabel,
  ROSTER_ACCEPT,
  ROSTER_OUTCOMES,
  rosterContentType,
  rosterHasChanges,
  rosterName,
  rosterSummary,
  suggestionQuery,
  suggestionStatus,
} from "./rosterHelpers";

function personName(person) {
  return person.display_name || person.email;
}

const WHEN = new Intl.DateTimeFormat(undefined, {
  month: "short",
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
});

function when(value) {
  const parsed = value ? new Date(value) : null;
  return parsed && !Number.isNaN(parsed.getTime()) ? WHEN.format(parsed) : "—";
}

// Names and emails from every QuizBurg account, as the organizer types.
function useStudentSuggestions(classId, text) {
  const api = useApi();
  const query = suggestionQuery(text);
  const [result, setResult] = useState({ query: "", items: [] });

  useEffect(() => {
    if (!query) return undefined;
    const controller = new AbortController();
    // Wait for a pause in typing before asking.
    const timer = window.setTimeout(async () => {
      try {
        const items = await api(
          `/classes/${classId}/student-suggestions?q=${encodeURIComponent(query)}`,
          { signal: controller.signal },
        );
        if (!controller.signal.aborted) {
          setResult({ query, items: Array.isArray(items) ? items : [] });
        }
      } catch {
        // Suggestions are a convenience; typing a full email still works.
        if (!controller.signal.aborted) setResult({ query, items: [] });
      }
    }, 250);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [api, classId, query]);

  return query && result.query === query ? result.items : [];
}

// "+ Add student" pop-up: invite one person (with name and email
// suggestions from the whole app), import the registrar's roster, and see or
// cancel the invitations still waiting to be accepted.
export function AddStudentDialog({ classInfo, onClose, onChange }) {
  const ref = useRef(null);
  const api = useApi();
  const action = useAction();
  const invites = useResource(`/classes/${classInfo.id}/invites`);
  const [text, setText] = useState("");
  const [added, setAdded] = useState(0);
  const [tab, setTab] = useState("invite");
  const suggestions = useStudentSuggestions(classInfo.id, text);
  const listId = useId();

  useEffect(() => {
    const dialog = ref.current;
    if (dialog && !dialog.open) dialog.showModal();
  }, []);

  async function inviteEmail(email) {
    const sent = await action.run(() =>
      api(`/classes/${classInfo.id}/invites`, {
        method: "POST",
        body: JSON.stringify({ email: email.trim() }),
      }),
    );
    if (sent) {
      setText("");
      setAdded((count) => count + 1);
      invites.reload();
    }
  }

  async function cancel(invitation) {
    const done = await action.run(async () => {
      await api(`/classes/${classInfo.id}/invites/${invitation.account_id}`, {
        method: "DELETE",
      });
      return true;
    });
    if (done) invites.reload();
  }

  const pending = Array.isArray(invites.data) ? invites.data : [];
  const closed = classInfo.archived;

  return (
    <dialog
      ref={ref}
      className="cl-dlg"
      aria-labelledby="cl-add-title"
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
          Add student{classInfo.code && <> · <b>{classInfo.code}</b></>}
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

      <div className="cl-view-switch cl-dlg-tabs" role="group" aria-label="Add how">
        <button
          type="button"
          aria-pressed={tab === "invite"}
          onClick={() => setTab("invite")}
        >
          Invite one
        </button>
        <button
          type="button"
          aria-pressed={tab === "roster"}
          onClick={() => setTab("roster")}
        >
          Import roster
        </button>
      </div>

      {tab === "roster" ? (
        <RosterImport
          classInfo={classInfo}
          onImported={() => {
            invites.reload();
            onChange?.();
          }}
        />
      ) : (
        <>
          <form
            className="cl-dlg-head"
            onSubmit={(event) => {
              event.preventDefault();
              void inviteEmail(text);
            }}
          >
            <h2 id="cl-add-title">Add a student to this class</h2>
            <div className="cl-dlg-row">
              <label className="cl-search">
                <span className="cl-sr">Name or email</span>
                <input
                  type="text"
                  inputMode="email"
                  placeholder="Start typing a name or email…"
                  value={text}
                  autoFocus
                  autoComplete="off"
                  required
                  role="combobox"
                  aria-expanded={suggestions.length > 0}
                  aria-controls={listId}
                  aria-autocomplete="list"
                  disabled={action.busy || closed}
                  onChange={(event) => setText(event.target.value)}
                />
              </label>
              <button
                type="submit"
                className="cl-add-one"
                disabled={action.busy || closed || !text.includes("@")}
                title="Invite this email address"
              >
                + Invite
              </button>
            </div>

            {suggestions.length > 0 && (
              <ul className="cl-suggest" id={listId} role="listbox" aria-label="Suggestions">
                {suggestions.map((person) => {
                  const status = suggestionStatus(person.membership_status);
                  return (
                    <li key={person.account_id} role="option" aria-selected="false">
                      <span className="cl-pav" aria-hidden="true">
                        {initials(personName(person))}
                      </span>
                      <span>
                        <strong className="cl-pname">{personName(person)}</strong>
                        <small className="cl-pmail">{person.email}</small>
                      </span>
                      {status.canInvite ? (
                        <button
                          type="button"
                          className="cl-secondary"
                          disabled={action.busy || closed}
                          onClick={() => void inviteEmail(person.email)}
                        >
                          Invite
                        </button>
                      ) : (
                        <span className="cl-tag is-me">{status.label}</span>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}

            <p>
              {closed
                ? "This class is archived, so no one new can join."
                : "Suggestions come from everyone with a QuizBurg account. They get an email and accept from their Classes page" +
                  (classInfo.code && classInfo.joiningOpen
                    ? `, or they can ask to join with code ${classInfo.code}.`
                    : ".")}
            </p>
            {action.error && (
              <p className="cl-dlg-error" role="alert">
                {action.error.message}
              </p>
            )}
          </form>

          <div className="cl-dlg-sub">
            <span>Waiting to accept</span>
            <span>
              {pending.length} {pending.length === 1 ? "person" : "people"}
            </span>
          </div>

          <div className="cl-people">
            {invites.loading ? (
              <p className="cl-dlg-empty" role="status">
                Loading invitations…
              </p>
            ) : invites.error ? (
              <p className="cl-dlg-empty" role="alert">
                {invites.error.message}{" "}
                <button type="button" onClick={invites.reload}>
                  Retry
                </button>
              </p>
            ) : pending.length === 0 ? (
              <p className="cl-dlg-empty">No pending invitations.</p>
            ) : (
              pending.map((invitation) => (
                <div className="cl-person" key={invitation.account_id}>
                  <span className="cl-pav" aria-hidden="true">
                    {initials(personName(invitation))}
                  </span>
                  <span>
                    <strong className="cl-pname">{personName(invitation)}</strong>
                    {invitation.display_name &&
                      invitation.display_name !== invitation.email && (
                        <small className="cl-pmail">{invitation.email}</small>
                      )}
                  </span>
                  <button
                    type="button"
                    className="cl-secondary"
                    disabled={action.busy}
                    onClick={() => void cancel(invitation)}
                  >
                    Cancel
                  </button>
                </div>
              ))
            )}
          </div>
        </>
      )}

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
    </dialog>
  );
}

// Upload the registrar's class list: a preview first (nothing saved), then
// the import itself.
function RosterImport({ classInfo, onImported }) {
  const api = useApi();
  const action = useAction();
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [done, setDone] = useState(null);

  function send(chosen, dryRun) {
    return api(
      `/classes/${classInfo.id}/roster/import?dry_run=${dryRun ? "true" : "false"}`,
      {
        method: "POST",
        body: chosen,
        headers: { "Content-Type": rosterContentType(chosen) },
      },
    );
  }

  async function choose(event) {
    const chosen = event.target.files?.[0] ?? null;
    event.target.value = "";
    setFile(chosen);
    setPreview(null);
    setDone(null);
    if (!chosen) return;
    const result = await action.run(() => send(chosen, true));
    if (result) setPreview(result);
  }

  async function confirm() {
    const result = await action.run(() => send(file, false));
    if (result) {
      setDone(result);
      setPreview(null);
      onImported?.();
    }
  }

  const shown = done ?? preview;

  return (
    <div className="cl-dlg-head cl-roster">
      <h2 id="cl-add-title">Import the class roster</h2>
      <p>
        Upload the class list from the registrar (CSV or Excel) with an ID and
        a Name column written Last,First. Students who already have an account
        are invited by email. Everyone else is remembered: when they ask to
        join with the class code, they are approved automatically.
      </p>

      <label className="cl-button cl-secondary cl-file">
        {file ? "Choose another file" : "Choose roster file"}
        <input
          type="file"
          accept={ROSTER_ACCEPT}
          disabled={action.busy || classInfo.archived}
          onChange={(event) => void choose(event)}
        />
      </label>
      {file && <small className="cl-pmail">{file.name}</small>}

      {action.busy && (
        <p role="status">{preview ? "Importing…" : "Reading the roster…"}</p>
      )}
      <RequestError error={action.error} />

      {shown && (
        <>
          <p role="status" aria-live="polite">
            {done ? "Imported: " : "Preview: "}
            {rosterSummary(shown.counts) || "nothing to change"}
            {done && ` · ${done.emails_sent} ${done.emails_sent === 1 ? "email" : "emails"} sent`}
          </p>

          {preview && (
            <div className="cl-actions">
              <button
                type="button"
                className="cl-add-one"
                disabled={action.busy || !rosterHasChanges(preview.counts)}
                onClick={() => void confirm()}
              >
                Import {preview.rows.length}{" "}
                {preview.rows.length === 1 ? "row" : "rows"}
              </button>
            </div>
          )}

          <div className="cl-table-wrap cl-roster-table">
            <table className="cl-table">
              <caption className="cl-sr">Roster rows</caption>
              <thead>
                <tr>
                  <th scope="col">Student</th>
                  <th scope="col">ID</th>
                  <th scope="col">Result</th>
                </tr>
              </thead>
              <tbody>
                {shown.rows.map((row) => (
                  <tr key={row.row_number}>
                    <td>
                      {rosterName(row)}
                      {row.account_name && <small>Account: {row.account_name}</small>}
                    </td>
                    <td>{row.student_number ?? "—"}</td>
                    <td>
                      <span
                        className={`cl-outcome is-${
                          ROSTER_OUTCOMES[row.outcome]?.tone ?? "none"
                        }`}
                      >
                        {outcomeLabel(row.outcome)}
                      </span>
                      {row.message && <small>{row.message}</small>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

        </>
      )}
    </div>
  );
}

// Approvals → Students: people who asked to join with the class code.
export function JoinRequestsTable({ classInfo, onChange }) {
  const api = useApi();
  const action = useAction();
  const requests = useResource(`/classes/${classInfo.id}/join-requests`);

  async function decide(path) {
    const done = await action.run(() =>
      api(`/classes/${classInfo.id}/join-requests/${path}`, { method: "POST" }),
    );
    if (done) {
      requests.reload();
      onChange?.();
    }
  }

  if (requests.loading) {
    return (
      <div className="cl-state" role="status">
        <h2>Loading join requests…</h2>
      </div>
    );
  }
  if (requests.error) {
    return <RequestError error={requests.error} retry={requests.reload} />;
  }

  const items = Array.isArray(requests.data) ? requests.data : [];

  return (
    <>
      <RequestError error={action.error} />
      <ReportTable
        caption="Join requests"
        rememberAs={`class:${classInfo.id}:join-requests`}
        noun="request"
        tableClass="cl-rows cl-approval-rows"
        columnClasses={["", "cl-wide", "", ""]}
        headers={["Status", "Student", "Asked", "Decision"]}
        emptyTitle="No one is waiting"
        emptyText="When someone joins with the class code, they show up here until you accept them."
        controls={
          <button
            type="button"
            className="cl-decide is-approve"
            disabled={action.busy || classInfo.archived || items.length === 0}
            onClick={() => void decide("approve-all")}
          >
            Accept all
          </button>
        }
        rows={items.map((item) => ({
          key: item.account_id,
          text: `${item.display_name} ${item.email}`,
          leadClass: "cl-status is-pending",
          cells: [
            "Waiting",
            <span className="cl-quiz-cell">
              <strong>{personName(item)}</strong>
              <small>{item.email}</small>
            </span>,
            when(item.requested_at),
            <span className="cl-approval">
              <button
                type="button"
                className="cl-decide is-approve"
                disabled={action.busy || classInfo.archived}
                onClick={() => void decide(`${item.account_id}/approve`)}
              >
                Accept
              </button>
              <button
                type="button"
                className="cl-decide"
                disabled={action.busy}
                onClick={() => void decide(`${item.account_id}/reject`)}
              >
                Reject
              </button>
            </span>,
          ],
        }))}
      />
    </>
  );
}
