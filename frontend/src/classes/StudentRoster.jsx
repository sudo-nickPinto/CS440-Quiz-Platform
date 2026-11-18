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

// "+ Add student" pop-up with two tabs:
// - Add student: search every QuizBurg account by name or email and add
//   them. Someone with an account is in the class right away (there is no
//   invitation to accept).
// - Add roster: drop in the registrar's class list, check the preview,
//   then import it.
export function AddStudentDialog({ classInfo, onClose, onChange }) {
  const ref = useRef(null);
  const [tab, setTab] = useState("student");
  const [added, setAdded] = useState(0);

  useEffect(() => {
    const dialog = ref.current;
    if (dialog && !dialog.open) dialog.showModal();
  }, []);

  return (
    <dialog
      ref={ref}
      className="cl-dlg cl-dlg-wide"
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
        <span id="cl-add-title">
          Add to {classInfo.name}
          {classInfo.code && <> · <b>{classInfo.code}</b></>}
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

      <div className="cl-add-tabs">
        <div
          className="cl-view-switch is-duo"
          role="group"
          aria-label="Add a student or a roster"
        >
          <button
            type="button"
            aria-pressed={tab === "student"}
            onClick={() => setTab("student")}
          >
            Add student
          </button>
          <button
            type="button"
            aria-pressed={tab === "roster"}
            onClick={() => setTab("roster")}
          >
            Add roster
          </button>
        </div>
      </div>

      <div className="cl-add-body">
        {classInfo.archived ? (
          <p className="cl-add-note">
            This class is archived, so no one new can join.
          </p>
        ) : tab === "roster" ? (
          <RosterImport classInfo={classInfo} onImported={onChange} />
        ) : (
          <StudentSearch
            classInfo={classInfo}
            onAdded={() => {
              setAdded((count) => count + 1);
              onChange?.();
            }}
          />
        )}
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
    </dialog>
  );
}

// Add student tab: the search box, and only the results under it.
function StudentSearch({ classInfo, onAdded }) {
  const api = useApi();
  const action = useAction();
  const [text, setText] = useState("");
  const [justAdded, setJustAdded] = useState({});
  const suggestions = useStudentSuggestions(classInfo.id, text);
  const listId = useId();
  const typedEmail = /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(text.trim());

  async function add(email) {
    const person = await action.run(() =>
      api(`/classes/${classInfo.id}/students`, {
        method: "POST",
        body: JSON.stringify({ email: email.trim() }),
      }),
    );
    if (person) {
      setJustAdded((map) => ({ ...map, [person.account_id]: true }));
      onAdded();
    }
  }

  return (
    <form
      className="cl-add-search"
      onSubmit={(event) => {
        event.preventDefault();
        if (typedEmail) void add(text);
      }}
    >
      <div className="cl-dlg-row">
        <label className="cl-search">
          <span className="cl-sr">Search by name or email</span>
          <input
            type="text"
            inputMode="email"
            placeholder="Search by name or email…"
            value={text}
            autoFocus
            autoComplete="off"
            role="combobox"
            aria-expanded={suggestions.length > 0}
            aria-controls={listId}
            aria-autocomplete="list"
            disabled={action.busy}
            onChange={(event) => setText(event.target.value)}
          />
        </label>
        {typedEmail && (
          <button type="submit" className="cl-add-one" disabled={action.busy}>
            + Add
          </button>
        )}
      </div>

      {action.error && (
        <p className="cl-dlg-error" role="alert">
          {action.error.message}
        </p>
      )}

      {suggestions.length > 0 && (
        <ul
          className="cl-suggest"
          id={listId}
          role="listbox"
          aria-label="Matching accounts"
        >
          {suggestions.map((person) => {
            const status = justAdded[person.account_id]
              ? { label: "Added", canAdd: false }
              : suggestionStatus(person.membership_status);
            return (
              <li key={person.account_id} role="option" aria-selected="false">
                <span className="cl-pav" aria-hidden="true">
                  {initials(personName(person))}
                </span>
                <span>
                  <strong className="cl-pname">{personName(person)}</strong>
                  <small className="cl-pmail">{person.email}</small>
                </span>
                {status.canAdd ? (
                  <button
                    type="button"
                    className="cl-secondary"
                    disabled={action.busy}
                    onClick={() => void add(person.email)}
                  >
                    Add
                  </button>
                ) : (
                  <span className="cl-tag is-me">{status.label}</span>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </form>
  );
}

// Add roster tab: drop the registrar's class list (CSV or Excel), see a
// preview (nothing saved), then import it.
function RosterImport({ classInfo, onImported }) {
  const api = useApi();
  const action = useAction();
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [done, setDone] = useState(null);
  const [dragging, setDragging] = useState(false);

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

  async function choose(chosen) {
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
    <div className="cl-roster">
      <label
        className={`cl-drop${dragging ? " is-over" : ""}`}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          const dropped = event.dataTransfer.files?.[0];
          if (dropped && !action.busy) void choose(dropped);
        }}
      >
        <input
          className="cl-sr"
          type="file"
          accept={ROSTER_ACCEPT}
          disabled={action.busy}
          onChange={(event) => {
            const chosen = event.target.files?.[0] ?? null;
            event.target.value = "";
            void choose(chosen);
          }}
        />
        <strong>
          {file ? file.name : "Drop the roster file here"}
        </strong>
        <span>
          {file ? "Drop another file, or click to choose one" : "or click to choose one"}
        </span>
        <small>CSV or Excel from the registrar, with ID and Name (Last,First).</small>
      </label>

      {action.busy && (
        <p role="status">{preview ? "Importing…" : "Reading the roster…"}</p>
      )}
      <RequestError error={action.error} />

      {shown && (
        <>
          <div className="cl-roster-bar">
            <p role="status" aria-live="polite">
              {done ? "Imported: " : "Preview: "}
              {rosterSummary(shown.counts) || "nothing to change"}
              {done &&
                ` · ${done.emails_sent} ${done.emails_sent === 1 ? "email" : "emails"} sent`}
            </p>
            {preview && (
              <button
                type="button"
                className="cl-add-one"
                disabled={action.busy || !rosterHasChanges(preview.counts)}
                onClick={() => void confirm()}
              >
                Import {preview.rows.length}{" "}
                {preview.rows.length === 1 ? "row" : "rows"}
              </button>
            )}
          </div>

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
export function JoinRequestsTable({ classInfo, onChange, switcher = null }) {
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
          <>
            <button
              type="button"
              className="cl-decide is-approve"
              disabled={action.busy || classInfo.archived || items.length === 0}
              onClick={() => void decide("approve-all")}
            >
              Accept all
            </button>
            {switcher}
          </>
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
