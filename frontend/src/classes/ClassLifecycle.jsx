import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router";

import { useAction, useApi } from "../authenticated-demo/rest";
import SelectMenu from "./SelectMenu";
import { matchesTyped } from "./trashHelpers";
import {
  compareSemesters,
  defaultSemester,
  labelSemesterChoices,
  newSemesterChoices,
} from "./semesters";
import "./class-lifecycle.css";

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

function Dialog({ id, label, busy, onCancel, className = "", children }) {
  const ref = useRef(null);
  useModal(ref);
  return (
    <dialog
      ref={ref}
      className={`qb-confirm cl-lifecycle-dialog ${className}`.trim()}
      aria-labelledby={id}
      onCancel={(event) => {
        event.preventDefault();
        if (!busy) onCancel();
      }}
    >
      <div className="qb-confirm-top">
        <span>{label}</span>
      </div>
      {children}
    </dialog>
  );
}

function DialogError({ error }) {
  if (!error) return null;
  return (
    <p className="cl-feedback cl-error" role="alert">
      {error.message}
    </p>
  );
}

// The extra step for destructive actions: type the class name (or a word)
// before the button works (matchesTyped).
function TypeToConfirm({ expected, value, onChange, disabled }) {
  return (
    <label className="cl-confirm-field">
      <span>
        Type <b>{expected}</b> to confirm
      </span>
      <input
        type="text"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        autoComplete="off"
        spellCheck={false}
        autoFocus
        disabled={disabled}
      />
    </label>
  );
}

// Archive is easy to undo, so it is a simple confirm. Moving a class to the
// trash and deleting it permanently are the steps that ask for the name.
export function ArchiveClassDialog({
  classInfo,
  busy,
  error,
  onCancel,
  onConfirm,
}) {
  return (
    <Dialog id="cl-archive-title" label="Archive class" busy={busy} onCancel={onCancel}>
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
        <DialogError error={error} />
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
    </Dialog>
  );
}

export function TrashClassDialog({ classInfo, busy, error, onCancel, onConfirm }) {
  const [typed, setTyped] = useState("");
  const matches = matchesTyped(typed, classInfo.name);

  return (
    <Dialog id="cl-trash-title" label="Move to trash" busy={busy} onCancel={onCancel}>
      <form
        className="qb-confirm-body"
        onSubmit={(event) => {
          event.preventDefault();
          if (matches) onConfirm();
        }}
      >
        <h2 id="cl-trash-title">Move {classInfo.name} to the trash?</h2>
        <p>
          Everyone loses access until you restore it from Classes → Trash.
          After 30 days it is deleted permanently and can&apos;t be restored.
        </p>
        <TypeToConfirm
          expected={classInfo.name}
          value={typed}
          onChange={setTyped}
          disabled={busy}
        />
        <DialogError error={error} />
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
    </Dialog>
  );
}

function plural(count, word) {
  return `${count} ${word}${count === 1 ? "" : "s"}`;
}

// Deleting from the trash can't be undone, so it always asks, and a class
// needs its name typed (or "delete" when several classes are picked).
export function PurgeDialog({ items, busy, error, onCancel, onConfirm }) {
  const [typed, setTyped] = useState("");
  const classes = items.filter((item) => item.kind === "class");
  const expected =
    classes.length === 1 ? classes[0].name : classes.length > 1 ? "delete" : null;
  const ready = expected === null || matchesTyped(typed, expected);
  const shown = items.slice(0, 5);

  return (
    <Dialog
      id="cl-purge-title"
      label="Delete permanently"
      busy={busy}
      onCancel={onCancel}
    >
      <form
        className="qb-confirm-body"
        onSubmit={(event) => {
          event.preventDefault();
          if (ready) onConfirm();
        }}
      >
        <h2 id="cl-purge-title">
          Delete {plural(items.length, "item")} forever?
        </h2>
        <p>This can&apos;t be undone. They won&apos;t come back from the trash.</p>
        <ul className="cl-purge-list">
          {shown.map((item) => (
            <li key={item.key}>
              <span className="cl-kind">{item.kindLabel}</span>
              {item.title}
            </li>
          ))}
          {items.length > shown.length && (
            <li className="cl-muted">and {items.length - shown.length} more</li>
          )}
        </ul>
        {classes.length > 0 && (
          <p>
            Deleting a class also deletes its quizzes and sessions that are in
            the trash.
          </p>
        )}
        {expected && (
          <TypeToConfirm
            expected={expected}
            value={typed}
            onChange={setTyped}
            disabled={busy}
          />
        )}
        <DialogError error={error} />
        <div className="qb-confirm-actions">
          <button
            type="button"
            className="qb-btn qb-btn-paper"
            disabled={busy}
            onClick={onCancel}
          >
            Keep them
          </button>
          <button
            type="submit"
            className="qb-btn cl-btn-danger"
            disabled={busy || !ready}
          >
            {busy ? "Deleting…" : `Delete ${plural(items.length, "item")}`}
          </button>
        </div>
      </form>
    </Dialog>
  );
}

function classPage(classId) {
  return `/app/classes/${classId}?view=admin`;
}

// The admin view's ⋯ → Semester: see which semester you're in, switch to
// another semester of this course, or start a new, empty one. Students
// never see this; the server only sends organizers the semester list.
export function SemesterDialog({ classInfo, onClose, onChanged }) {
  const api = useApi();
  const action = useAction();
  const navigate = useNavigate();

  const semesters = [...(classInfo.semesters ?? [])].sort(
    (a, b) => compareSemesters(b.semester, a.semester) || b.class_id - a.class_id,
  );
  const labels = semesters.map((item) => item.semester);
  const newChoices = newSemesterChoices(labels);
  const [newSemester, setNewSemester] = useState(newChoices[0]);
  const labelChoices = labelSemesterChoices(labels);
  const [label, setLabel] = useState(defaultSemester(labelChoices));

  function go(classId) {
    onClose();
    navigate(classPage(classId));
  }

  async function startSemester(event) {
    event.preventDefault();
    const created = await action.run(() =>
      api(`/classes/${classInfo.id}/semesters`, {
        method: "POST",
        body: JSON.stringify({ semester: newSemester }),
      }),
    );
    if (created) go(created.class_id);
  }

  async function saveLabel(event) {
    event.preventDefault();
    const saved = await action.run(async () => {
      await api(`/classes/${classInfo.id}`, {
        method: "PATCH",
        body: JSON.stringify({ semester: label }),
      });
      return true;
    });
    if (saved) onChanged();
  }

  return (
    <Dialog
      id="cl-semester-title"
      label="Semester"
      busy={action.busy}
      onCancel={onClose}
      className="cl-semester-dialog"
    >
      <div className="qb-confirm-body">
        <h2 id="cl-semester-title">{classInfo.name}</h2>

        {!classInfo.semester ? (
          // Classes made before semesters existed: label this one first, so
          // every semester of the course has a name.
          <form className="cl-sem-new" onSubmit={saveLabel}>
            <p>
              Which semester is this class? Every semester of a course needs
              one before you can start another.
            </p>
            <div className="cl-sem-new-row">
              <SelectMenu
                label="Semester"
                value={label}
                options={labelChoices.map((item) => ({ value: item, label: item }))}
                onChange={setLabel}
                disabled={action.busy}
              />
              <button
                type="submit"
                className="qb-btn"
                disabled={action.busy || !label}
              >
                {action.busy ? "Saving…" : "Save semester"}
              </button>
            </div>
          </form>
        ) : (
          <>
            <p className="cl-sem-current">
              You&apos;re managing <b>{classInfo.semester}</b>. Each semester
              has its own code, students, quizzes and grades.
            </p>

            <ul className="cl-sem-list" aria-label="Semesters of this course">
              {semesters.map((item) => {
                const current = item.class_id === classInfo.id;
                return (
                  <li key={item.class_id} className={current ? "is-current" : ""}>
                    {/* A semester made before labels existed has none yet;
                        opening it and choosing ⋯ → Semester labels it. */}
                    <span
                      className={"cl-sem-name" + (item.semester ? "" : " is-none")}
                    >
                      {item.semester ?? "No semester"}
                    </span>
                    {item.archived && <span className="cl-sem-tag">Archived</span>}
                    {current ? (
                      <span className="cl-sem-tag is-current">Current</span>
                    ) : (
                      <button
                        type="button"
                        className="cl-sem-switch"
                        disabled={action.busy}
                        onClick={() => go(item.class_id)}
                      >
                        Switch →
                      </button>
                    )}
                  </li>
                );
              })}
            </ul>

            <form className="cl-sem-new" onSubmit={startSemester}>
              <h3>Start a new semester</h3>
              <p>
                It starts empty, with a new class code and no students or
                quizzes. This semester keeps its history.
              </p>
              <div className="cl-sem-new-row">
                <SelectMenu
                  label="New semester"
                  value={newSemester}
                  options={newChoices.map((item) => ({ value: item, label: item }))}
                  onChange={setNewSemester}
                  disabled={action.busy}
                />
                <button
                  type="submit"
                  className="qb-btn"
                  disabled={action.busy || !newSemester}
                >
                  {action.busy ? "Starting…" : `Start ${newSemester}`}
                </button>
              </div>
            </form>
          </>
        )}

        <DialogError error={action.error} />

        <div className="qb-confirm-actions">
          <button
            type="button"
            className="qb-btn qb-btn-paper"
            disabled={action.busy}
            onClick={onClose}
          >
            Close
          </button>
        </div>
      </div>
    </Dialog>
  );
}
