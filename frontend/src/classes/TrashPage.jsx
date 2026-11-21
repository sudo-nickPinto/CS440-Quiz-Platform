import { useState } from "react";
import { Link, Navigate } from "react-router";

import { useAccount } from "../authenticated-demo/account";
import RequestError from "../authenticated-demo/RequestError";
import { useAction, useApi, useResource } from "../authenticated-demo/rest";
import { shortName } from "./classHelpers";
import { PurgeDialog } from "./ClassLifecycle";
import { trashRows, trashSelection } from "./trashHelpers";
import "./class-lifecycle.css";

export default function TrashPage() {
  const account = useAccount();
  // Only faculty organize classes, so the trash is theirs. Students who type
  // the address go back to their classes.
  if (account.is_active !== true || account.role !== "ADMIN") {
    return <Navigate to="/app/classes" replace />;
  }
  return <Trash />;
}

function Trash() {
  const api = useApi();
  const action = useAction();
  const resource = useResource("/trash");
  const [picked, setPicked] = useState(() => new Set());
  // The rows waiting for "Delete permanently" to be confirmed.
  const [purging, setPurging] = useState(null);

  const data = resource.data;
  const rows = trashRows(data);
  const pickedRows = rows.filter((row) => picked.has(row.key));
  const allPicked = rows.length > 0 && pickedRows.length === rows.length;

  function toggle(key) {
    setPicked((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  async function send(path, selected) {
    if (selected.length === 0) return false;
    const ok = await action.run(async () => {
      await api(path, {
        method: "POST",
        body: JSON.stringify(trashSelection(selected)),
      });
      return true;
    });
    if (!ok) return false;
    setPicked(new Set());
    resource.reload();
    return true;
  }

  async function purge() {
    if (await send("/trash/purge", purging)) setPurging(null);
  }

  return (
    <section className="cl-page cl-trash-page" aria-labelledby="trash-heading">
      {purging && (
        <PurgeDialog
          items={purging}
          busy={action.busy}
          error={action.error}
          onCancel={() => {
            action.clearError();
            setPurging(null);
          }}
          onConfirm={() => void purge()}
        />
      )}

      <div className="cl-titlebar cl-trash-titlebar">
        <Link className="cl-titlebar-back" to="/app/classes">
          <span aria-hidden="true">←</span> Classes
        </Link>
        <h1 id="trash-heading">
          Trash
          {data && (
            <small>
              {rows.length} {rows.length === 1 ? "item" : "items"} · kept for 30
              days
            </small>
          )}
        </h1>
      </div>

      {rows.length > 0 && (
        <div className="cl-toolbar cl-trash-toolbar">
          <label className="cl-check-all">
            <input
              type="checkbox"
              checked={allPicked}
              onChange={() =>
                setPicked(
                  allPicked ? new Set() : new Set(rows.map((row) => row.key)),
                )
              }
            />
            <span>Select all</span>
          </label>
          <span className="cl-picked" aria-live="polite">
            {pickedRows.length} selected
          </span>
          <button
            type="button"
            disabled={action.busy || pickedRows.length === 0}
            onClick={() => void send("/trash/restore", pickedRows)}
          >
            Restore
          </button>
          <button
            type="button"
            className="cl-danger"
            disabled={action.busy || pickedRows.length === 0}
            onClick={() => setPurging(pickedRows)}
          >
            Delete permanently
          </button>
        </div>
      )}

      {resource.loading && (
        <p className="cl-state" role="status">
          Loading the trash…
        </p>
      )}
      <RequestError error={resource.error} retry={resource.reload} />
      {!purging && <RequestError error={action.error} />}

      {data && rows.length === 0 && (
        <div className="cl-state">
          <h2>Trash is empty</h2>
          <p>
            Classes, quizzes and sessions you move to the trash stay here for
            30 days, so you can restore them.
          </p>
        </div>
      )}

      {rows.length > 0 && (
        <div className="cl-grid">
          {rows.map((row) => (
            <article
              className={`cl-card cl-trash-card${
                picked.has(row.key) ? " is-picked" : ""
              }`}
              key={row.key}
            >
              <div className="cl-card-banner">
                <span className="cl-role">
                  {row.kindLabel}
                </span>
                <label className="cl-card-check">
                  <input
                    type="checkbox"
                    checked={picked.has(row.key)}
                    onChange={() => toggle(row.key)}
                    aria-label={`Select ${row.kindLabel.toLowerCase()} ${row.title}`}
                  />
                </label>
                <span className="cl-card-code">{shortName(row.title)}</span>
              </div>

              <div className="cl-card-body">
                <h2>{row.title}</h2>
                {row.detail && <p className="cl-card-semester">{row.detail}</p>}
                <p className={`cl-days${row.soon ? " is-soon" : ""}`}>
                  {row.days}
                </p>
                {row.blocked && (
                  <p className="cl-muted">Restore its class first.</p>
                )}
                <div className="cl-card-actions">
                  <button
                    type="button"
                    disabled={action.busy || row.blocked}
                    onClick={() => void send("/trash/restore", [row])}
                  >
                    Restore
                  </button>
                  <button
                    type="button"
                    className="cl-danger"
                    disabled={action.busy}
                    onClick={() => setPurging([row])}
                  >
                    Delete permanently
                  </button>
                </div>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
