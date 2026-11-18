import { useState } from "react";
import { Link } from "react-router";

import RequestError from "../authenticated-demo/RequestError";
import { useAction, useApi, useResource } from "../authenticated-demo/rest";
import { classLabel } from "./semesters";
import "./class-lifecycle.css";

const WHEN = new Intl.DateTimeFormat(undefined, {
  month: "short",
  day: "numeric",
  year: "numeric",
  hour: "numeric",
  minute: "2-digit",
});

function deletedOn(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : `Deleted ${WHEN.format(date)}`;
}

function TrashRow({ title, details, blockedBy, busy, onRestore, label }) {
  return (
    <li className="cl-trash-row">
      <div>
        <strong>{title}</strong>
        <small>{details.filter(Boolean).join(" · ")}</small>
        {blockedBy && (
          <small className="cl-trash-blocked">
            {blockedBy} is in the trash too. Restore the class first.
          </small>
        )}
      </div>
      <button
        type="button"
        disabled={busy || Boolean(blockedBy)}
        aria-label={`Restore ${label}`}
        onClick={onRestore}
      >
        Restore
      </button>
    </li>
  );
}

function TrashGroup({ title, children }) {
  return (
    <section className="cl-trash-group" aria-label={title}>
      <h3>{title}</h3>
      <ul>{children}</ul>
    </section>
  );
}

// Classes → Trash: what the caller moved to the trash (or, for classes, any
// organizer of theirs did), with a Restore button for each. Nothing in the
// trash is gone; restoring puts it back exactly as it was.
export default function TrashPanel({ onRestored, onClose }) {
  const api = useApi();
  const action = useAction();
  const resource = useResource("/trash");
  const [restored, setRestored] = useState(null);

  async function restore(path, done) {
    const ok = await action.run(async () => {
      await api(`${path}/restore`, { method: "POST" });
      return true;
    });
    if (!ok) return;
    setRestored(done);
    resource.refresh();
    onRestored?.();
  }

  const data = resource.data;
  const empty =
    data &&
    data.classes.length === 0 &&
    data.quizzes.length === 0 &&
    data.sessions.length === 0;

  return (
    <section
      id="class-trash-panel"
      className="cl-inline-panel cl-trash"
      aria-labelledby="class-trash-heading"
    >
      <h2 id="class-trash-heading">Trash</h2>
      <p>
        Classes, quizzes and hosted sessions you deleted. Restoring puts them
        back with all their students, results and grades.
      </p>

      {resource.loading && <p role="status">Loading the trash…</p>}
      <RequestError error={resource.error} retry={resource.reload} />
      <RequestError error={action.error} />

      {restored && !action.error && (
        <p className="cl-feedback" role="status">
          Restored {restored.label}.{" "}
          {restored.to && <Link to={restored.to}>Open it →</Link>}
        </p>
      )}

      {empty && (
        <p className="cl-trash-empty">
          The trash is empty. When you delete a class, a quiz or a hosted
          session, it waits here until you restore it.
        </p>
      )}

      {data?.classes.length > 0 && (
        <TrashGroup title="Classes">
          {data.classes.map((item) => (
            <TrashRow
              key={item.class_id}
              title={classLabel(item)}
              label={classLabel(item)}
              details={[item.archived && "Archived", deletedOn(item.deleted_at)]}
              busy={action.busy}
              onRestore={() =>
                void restore(`/classes/${item.class_id}`, {
                  label: classLabel(item),
                  to: `/app/classes/${item.class_id}`,
                })
              }
            />
          ))}
        </TrashGroup>
      )}

      {data?.quizzes.length > 0 && (
        <TrashGroup title="Quizzes">
          {data.quizzes.map((item) => (
            <TrashRow
              key={item.quiz_id}
              title={item.title}
              label={item.title}
              details={[item.class_name, deletedOn(item.deleted_at)]}
              blockedBy={item.class_in_trash ? item.class_name : null}
              busy={action.busy}
              onRestore={() =>
                void restore(`/quizzes/${item.quiz_id}`, {
                  label: item.title,
                  to: `/app/quizzes/${item.quiz_id}`,
                })
              }
            />
          ))}
        </TrashGroup>
      )}

      {data?.sessions.length > 0 && (
        <TrashGroup title="Hosted sessions">
          {data.sessions.map((item) => (
            <TrashRow
              key={item.session_id}
              title={`${item.quiz_title} · Session #${item.session_id}`}
              label={`session #${item.session_id} of ${item.quiz_title}`}
              details={[
                item.class_name,
                item.status === "CANCELLED" ? "Cancelled" : "Completed",
                deletedOn(item.deleted_at),
              ]}
              blockedBy={item.class_in_trash ? item.class_name : null}
              busy={action.busy}
              onRestore={() =>
                void restore(`/sessions/${item.session_id}`, {
                  label: `session #${item.session_id} of ${item.quiz_title}`,
                  to: `/app/quizzes/${item.quiz_id}/reports`,
                })
              }
            />
          ))}
        </TrashGroup>
      )}

      <button type="button" onClick={onClose}>
        Close
      </button>
    </section>
  );
}
