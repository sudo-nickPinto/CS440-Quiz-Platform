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
        Students can see the class on their list, but only organizers can
        open its quizzes, reports and grades. You can unarchive it later.
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

// Archive is easy to undo. Moving a class to the trash is the step that
// asks for the class name.
export function ArchiveClassDialog({
  classInfo,
  busy,
  error,
  onCancel,
  onConfirm,
}) {
  const ref = useRef(null);
  useModal(ref);

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
          onConfirm();
        }}
      >
        <h2 id="cl-archive-title">Archive {classInfo.name}?</h2>
        <p>
          The class code stops working and no new quizzes or sessions can
          start. Students can still see the class, but only organizers can
          open quizzes, reports and grades. You can unarchive it later.
        </p>

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
          <button type="submit" className="qb-btn" disabled={busy}>
            {busy ? "Archiving…" : "Archive class"}
          </button>
        </div>
      </form>
    </dialog>
  );
}

// Another empty semester of this same course. The name stays; only the
// semester is chosen.
export function NewSemesterDialog({ classInfo, onClose }) {
  const ref = useRef(null);
  const api = useApi();
  const action = useAction();
  const navigate = useNavigate();
  const options = semesterOptions();
  const suggested = nextSemester(classInfo.semester);
  const [semester, setSemester] = useState(suggested);
  const [custom, setCustom] = useState(false);
  useModal(ref);

  async function create(event) {
    event.preventDefault();
    const label = semester.trim();
    if (!label) return;
    const created = await action.run(() =>
      api(`/classes/${classInfo.id}/semesters`, {
        method: "POST",
        body: JSON.stringify({ semester: label }),
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
          {classInfo.name} gets another semester with its own code. It starts
          empty: no students and no quizzes. This semester keeps its history.
        </p>

        <label className="cl-confirm-field">
          <span>Semester</span>
          <select
            value={custom ? "custom" : semester}
            disabled={action.busy}
            onChange={(event) => {
              if (event.target.value === "custom") {
                setCustom(true);
                setSemester("");
              } else {
                setCustom(false);
                setSemester(event.target.value);
              }
            }}
          >
            {[...new Set([suggested, ...options])].map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
            <option value="custom">Other…</option>
          </select>
        </label>
        {custom && (
          <label className="cl-confirm-field">
            <span>Custom semester</span>
            <input
              type="text"
              value={semester}
              onChange={(event) => setSemester(event.target.value)}
              maxLength={30}
              required
              autoFocus
              disabled={action.busy}
            />
          </label>
        )}

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
            disabled={action.busy || !semester.trim()}
          >
            {action.busy ? "Creating…" : "Start semester"}
          </button>
        </div>
      </form>
    </dialog>
  );
}

export function TrashClassDialog({ classInfo, busy, error, onCancel, onConfirm }) {
  const ref = useRef(null);
  const [typed, setTyped] = useState("");
  useModal(ref);
  const matches =
    typed.trim().toLowerCase() === classInfo.name.trim().toLowerCase();

  return (
    <dialog
      ref={ref}
      className="qb-confirm cl-lifecycle-dialog"
      aria-labelledby="cl-trash-title"
      onCancel={(event) => {
        event.preventDefault();
        if (!busy) onCancel();
      }}
    >
      <div className="qb-confirm-top">
        <span>Move to trash</span>
      </div>
      <form
        className="qb-confirm-body"
        onSubmit={(event) => {
          event.preventDefault();
          if (matches) onConfirm();
        }}
      >
        <h2 id="cl-trash-title">Move {classInfo.name} to the trash?</h2>
        <p>
          Everyone loses access until you restore it. After 30 days it is
          deleted permanently and cannot be restored.
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
            Keep it
          </button>
          <button type="submit" className="qb-btn" disabled={busy || !matches}>
            {busy ? "Moving…" : "Move to trash"}
          </button>
        </div>
      </form>
    </dialog>
  );
}
