import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router";

import { useAction, useApi } from "../authenticated-demo/rest";
import { nextSemester, semesterOptions } from "./semesters";
import "./class-lifecycle.css";

// Suggestions for a semester box (<input list={id}>): this semester and the
// next two. Any other text is allowed too.
export function SemesterOptions({ id }) {
  return (
    <datalist id={id}>
      {semesterOptions().map((option) => (
        <option key={option} value={option} />
      ))}
    </datalist>
  );
}

// Shown at the top of an archived class: everything below it is grayed out
// (.cl-page.is-archived) and read-only.
export function ArchivedBanner({ classInfo, busy, onUnarchive }) {
  return (
    <div className="cl-archived-banner">
      <p>
        <b>Archived</b>{" "}
        {classInfo.semester ? `${classInfo.semester}. ` : ""}
        Reports and grades are still here, but no one can join and no new
        quizzes or sessions can start.
      </p>

      {classInfo.canManage && (
        <button type="button" disabled={busy} onClick={onUnarchive}>
          Unarchive class
        </button>
      )}
    </div>
  );
}

function useModal(ref) {
  useEffect(() => {
    const dialog = ref.current;
    if (dialog && !dialog.open) dialog.showModal();
  }, [ref]);
}

// Archiving is easy to undo now, but it still stops the class code, so the
// organizer types the class name first.
export function ArchiveClassDialog({
  classInfo,
  busy,
  error,
  onCancel,
  onConfirm,
}) {
  const ref = useRef(null);
  const [typed, setTyped] = useState("");
  useModal(ref);

  const matches =
    typed.trim().toLowerCase() === classInfo.name.trim().toLowerCase();

  return (
    <dialog
      ref={ref}
      className="qb-confirm cl-lifecycle-dialog"
      aria-labelledby="cl-archive-title"
      onCancel={(event) => {
        event.preventDefault();
        if (!busy) onCancel();
      }}
    >
      <div className="qb-confirm-top">
        <span>Archive class</span>
      </div>

      <form
        className="qb-confirm-body"
        onSubmit={(event) => {
          event.preventDefault();
          if (matches) onConfirm();
        }}
      >
        <h2 id="cl-archive-title">Archive {classInfo.name}?</h2>
        <p>
          The class code stops working and no new quizzes or sessions can
          start. Reports and grades stay available, and you can unarchive the
          class later from More.
        </p>

        <label className="cl-confirm-field">
          <span>
            Type <b>{classInfo.name}</b> to confirm
          </span>
          <input
            type="text"
            value={typed}
            onChange={(event) => setTyped(event.target.value)}
            autoComplete="off"
            spellCheck={false}
            autoFocus
            disabled={busy}
          />
        </label>

        {error && (
          <p className="cl-feedback cl-error" role="alert">
            {error.message}
          </p>
        )}

        <div className="qb-confirm-actions">
          <button
            type="button"
            className="qb-btn qb-btn-paper"
            disabled={busy}
            onClick={onCancel}
          >
            Keep it active
          </button>
          <button type="submit" className="qb-btn" disabled={busy || !matches}>
            {busy ? "Archiving…" : "Archive class"}
          </button>
        </div>
      </form>
    </dialog>
  );
}

// The same course again in another semester: a separate class with its own
// code, students and grades. The old class keeps its history.
export function NewSemesterDialog({ classInfo, onClose }) {
  const ref = useRef(null);
  const api = useApi();
  const action = useAction();
  const navigate = useNavigate();
  const [name, setName] = useState(classInfo.name);
  const [semester, setSemester] = useState(() =>
    nextSemester(classInfo.semester),
  );
  useModal(ref);

  async function create(event) {
    event.preventDefault();
    const created = await action.run(() =>
      api("/classes", {
        method: "POST",
        body: JSON.stringify({ name: name.trim(), semester: semester.trim() }),
      }),
    );
    if (created) navigate(`/app/classes/${created.class_id}`);
  }

  return (
    <dialog
      ref={ref}
      className="qb-confirm cl-lifecycle-dialog"
      aria-labelledby="cl-semester-title"
      onCancel={(event) => {
        event.preventDefault();
        if (!action.busy) onClose();
      }}
    >
      <div className="qb-confirm-top">
        <span>New semester</span>
      </div>

      <form className="qb-confirm-body" onSubmit={create}>
        <h2 id="cl-semester-title">Start a new semester</h2>
        <p>
          A new class with its own code, students and grades.{" "}
          {classInfo.name}
          {classInfo.semester ? ` (${classInfo.semester})` : ""} keeps its
          history; archive it when its semester is over.
        </p>

        <label className="cl-confirm-field">
          <span>Class name</span>
          <input
            type="text"
            value={name}
            onChange={(event) => setName(event.target.value)}
            maxLength={100}
            required
            disabled={action.busy}
          />
        </label>

        <label className="cl-confirm-field">
          <span>Semester</span>
          <input
            type="text"
            list="cl-new-semester-options"
            value={semester}
            onChange={(event) => setSemester(event.target.value)}
            maxLength={30}
            placeholder="Spring 2027"
            disabled={action.busy}
          />
        </label>
        <SemesterOptions id="cl-new-semester-options" />

        {action.error && (
          <p className="cl-feedback cl-error" role="alert">
            {action.error.message}
          </p>
        )}

        <div className="qb-confirm-actions">
          <button
            type="button"
            className="qb-btn qb-btn-paper"
            disabled={action.busy}
            onClick={onClose}
          >
            Cancel
          </button>
          <button
            type="submit"
            className="qb-btn"
            disabled={action.busy || !name.trim()}
          >
            {action.busy ? "Creating…" : "Create class"}
          </button>
        </div>
      </form>
    </dialog>
  );
}
