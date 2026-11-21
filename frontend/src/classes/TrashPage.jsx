import { useState } from "react";
import { Link } from "react-router";

import RequestError from "../authenticated-demo/RequestError";
import { useAction, useApi, useResource } from "../authenticated-demo/rest";
import { classLabel } from "./semesters";
import "./class-lifecycle.css";

function daysLeft(item) {
  const days = item.days_left;
  if (days == null) return "";
  if (days <= 1) return "1 day left";
  return `${days} days left`;
}

export default function TrashPage() {
  const api = useApi();
  const action = useAction();
  const resource = useResource("/trash");
  const [picked, setPicked] = useState(() => new Set());

  const data = resource.data;
  const rows = data
    ? [
        ...data.classes.map((item) => ({
          key: `class:${item.class_id}`,
          kind: "class",
          id: item.class_id,
          title: classLabel(item),
          detail: daysLeft(item),
        })),
        ...data.quizzes.map((item) => ({
          key: `quiz:${item.quiz_id}`,
          kind: "quiz",
          id: item.quiz_id,
          title: item.title,
          detail: [item.class_name, daysLeft(item)].filter(Boolean).join(" · "),
          blocked: item.class_in_trash,
        })),
        ...data.sessions.map((item) => ({
          key: `session:${item.session_id}`,
          kind: "session",
          id: item.session_id,
          title: `${item.quiz_title} · Session #${item.session_id}`,
          detail: [item.class_name, daysLeft(item)].filter(Boolean).join(" · "),
          blocked: item.class_in_trash,
        })),
      ]
    : [];

  const allPicked = rows.length > 0 && rows.every((row) => picked.has(row.key));

  function toggle(key) {
    setPicked((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function selection() {
    const body = { class_ids: [], quiz_ids: [], session_ids: [] };
    for (const row of rows) {
      if (!picked.has(row.key)) continue;
      if (row.kind === "class") body.class_ids.push(row.id);
      if (row.kind === "quiz") body.quiz_ids.push(row.id);
      if (row.kind === "session") body.session_ids.push(row.id);
    }
    return body;
  }

  async function run(path) {
    const body = selection();
    if (
      body.class_ids.length + body.quiz_ids.length + body.session_ids.length ===
      0
    ) {
      return;
    }
    const ok = await action.run(async () => {
      await api(path, { method: "POST", body: JSON.stringify(body) });
      return true;
    });
    if (!ok) return;
    setPicked(new Set());
    resource.reload();
  }

  return (
    <section className="cl-page cl-trash-page" aria-labelledby="trash-heading">
      <p>
        <Link to="/app/classes">← Classes</Link>
      </p>
      <div className="cl-title-row">
        <h1 id="trash-heading">Trash</h1>
      </div>
      <p className="cl-muted">
        Deleted classes, quizzes and sessions stay here for 30 days. Then they
        are deleted permanently.
      </p>

      {resource.loading && <p role="status">Loading the trash…</p>}
      <RequestError error={resource.error} retry={resource.reload} />
      <RequestError error={action.error} />

      {rows.length > 0 && (
        <div className="cl-toolbar">
          <label>
            <input
              type="checkbox"
              checked={allPicked}
              onChange={() =>
                setPicked(allPicked ? new Set() : new Set(rows.map((row) => row.key)))
              }
            />{" "}
            Select all
          </label>
          <button
            type="button"
            disabled={action.busy || picked.size === 0}
            onClick={() => void run("/trash/restore")}
          >
            Restore
          </button>
          <button
            type="button"
            disabled={action.busy || picked.size === 0}
            onClick={() => void run("/trash/purge")}
          >
            Delete permanently
          </button>
        </div>
      )}

      {data && rows.length === 0 && (
        <div className="cl-state">
          <h2>Trash is empty</h2>
          <p>Deleted classes, quizzes and sessions show up here.</p>
        </div>
      )}

      <div className="cl-grid">
        {rows.map((row) => (
          <article className="cl-card cl-card-archived" key={row.key}>
            <div className="cl-card-body">
              <label>
                <input
                  type="checkbox"
                  checked={picked.has(row.key)}
                  onChange={() => toggle(row.key)}
                  aria-label={`Select ${row.title}`}
                />
              </label>
              <h2>{row.title}</h2>
              <p className="cl-muted">{row.detail}</p>
              {row.blocked && (
                <p className="cl-muted">Restore the class before this item.</p>
              )}
              <div className="cl-actions">
                <button
                  type="button"
                  disabled={action.busy || row.blocked}
                  onClick={() => {
                    setPicked(new Set([row.key]));
                    const body = {
                      class_ids: row.kind === "class" ? [row.id] : [],
                      quiz_ids: row.kind === "quiz" ? [row.id] : [],
                      session_ids: row.kind === "session" ? [row.id] : [],
                    };
                    void action
                      .run(async () => {
                        await api("/trash/restore", {
                          method: "POST",
                          body: JSON.stringify(body),
                        });
                        return true;
                      })
                      .then((ok) => ok && resource.reload());
                  }}
                >
                  Restore
                </button>
                <button
                  type="button"
                  disabled={action.busy}
                  onClick={() => {
                    const body = {
                      class_ids: row.kind === "class" ? [row.id] : [],
                      quiz_ids: row.kind === "quiz" ? [row.id] : [],
                      session_ids: row.kind === "session" ? [row.id] : [],
                    };
                    void action
                      .run(async () => {
                        await api("/trash/purge", {
                          method: "POST",
                          body: JSON.stringify(body),
                        });
                        return true;
                      })
                      .then((ok) => ok && resource.reload());
                  }}
                >
                  Delete permanently
                </button>
              </div>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
