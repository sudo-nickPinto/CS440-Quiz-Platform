import { useState } from "react";
import { Link, useNavigate } from "react-router";

import { useAction, useApi } from "../authenticated-demo/rest";
import { useClassesResource } from "./classResources";
import { ClassCard, EmptyMessage, ResourceMessage } from "./ClassUI";

export default function ClassesPage() {
  const api = useApi();
  const action = useAction();
  const navigate = useNavigate();
  const resource = useClassesResource();

  const [panel, setPanel] = useState(null);
  const [name, setName] = useState("");
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const [sort, setSort] = useState("name");

  const ready = resource.status === "ready";
  const records = ready ? resource.data : [];

  const invitations = records.filter(
    (item) => item.membershipStatus === "INVITED",
  );

  const classes = records.filter(
    (item) => item.membershipStatus !== "INVITED",
  );

  const visible = classes
    .filter((item) =>
      item.name.toLowerCase().includes(query.trim().toLowerCase()),
    )
    .filter((item) => {
      if (filter === "managed") return item.canManage;
      if (filter === "member") return !item.canManage;
      if (filter === "archived") return item.archived;
      return true;
    })
    .sort((a, b) =>
      sort === "name-desc"
        ? b.name.localeCompare(a.name)
        : a.name.localeCompare(b.name),
    );

  function togglePanel(nextPanel) {
    setPanel((current) => (current === nextPanel ? null : nextPanel));
  }

  async function createClass(event) {
    event.preventDefault();

    const trimmedName = name.trim();
    if (!trimmedName) return;

    const created = await action.run(() =>
      api("/classes", {
        method: "POST",
        body: JSON.stringify({ name: trimmedName }),
      }),
    );

    if (created) {
      navigate(`/app/classes/${created.class_id}`);
    }
  }

  async function respondToInvitation(classId, decision) {
    const succeeded = await action.run(async () => {
      await api(`/classes/${classId}/invite/${decision}`, {
        method: "POST",
      });

      // Declining returns HTTP 204, so return our own success value.
      return true;
    });

    if (!succeeded) return;

    if (decision === "accept") {
      navigate(`/app/classes/${classId}`);
    } else {
      resource.reload();
    }
  }

  return (
    <section className="cl-page" aria-labelledby="classes-heading">
      <div className="cl-titlebar">
        <h1 id="classes-heading">
          Classes
          {ready && <small>{classes.length} total</small>}
        </h1>

        <button
          type="button"
          className="cl-new"
          aria-expanded={panel === "create"}
          aria-controls="class-create-panel"
          onClick={() => togglePanel("create")}
          disabled={action.busy}
        >
          + New class
        </button>

        <button
          type="button"
          className="cl-join"
          aria-expanded={panel === "join"}
          aria-controls="class-join-panel"
          onClick={() => togglePanel("join")}
        >
          Join
        </button>
      </div>

      {action.error && (
        <p className="cl-feedback cl-error" role="alert">
          {action.error.message}
        </p>
      )}

      {panel === "create" && (
        <form
          id="class-create-panel"
          className="cl-inline-panel"
          onSubmit={createClass}
        >
          <h2>New class</h2>

          <label>
            Class name
            <input
              type="text"
              value={name}
              onChange={(event) => setName(event.target.value)}
              maxLength={100}
              required
              disabled={action.busy}
            />
          </label>

          <button
            type="submit"
            disabled={action.busy || !name.trim()}
          >
            {action.busy ? "Saving…" : "Create class →"}
          </button>

          <button
            type="button"
            onClick={() => setPanel(null)}
            disabled={action.busy}
          >
            Close
          </button>
        </form>
      )}

      {panel === "join" && (
        <section id="class-join-panel" className="cl-inline-panel">
          <h2>Join a class</h2>
          <p>
            Accept an invitation below to join a class. Joining by
            class code is not available yet.
          </p>
          <button type="button" onClick={() => setPanel(null)}>
            Close
          </button>
        </section>
      )}

      {ready && invitations.length > 0 && (
        <section
          className="cl-invitations"
          aria-labelledby="class-invitations-heading"
        >
          <h2 id="class-invitations-heading">Class invitations</h2>

          {invitations.map((item) => (
            <article className="cl-invitation" key={item.id}>
              <div>
                <h3>{item.name}</h3>
                <p>
                  You have been invited to join this class.
                  {item.archived && " This class is archived."}
                </p>
              </div>

              <div className="cl-actions">
                <button
                  type="button"
                  disabled={action.busy}
                  onClick={() =>
                    respondToInvitation(item.id, "accept")
                  }
                >
                  Accept
                </button>

                <button
                  type="button"
                  disabled={action.busy}
                  onClick={() =>
                    respondToInvitation(item.id, "decline")
                  }
                >
                  Decline
                </button>
              </div>
            </article>
          ))}
        </section>
      )}

      <div className="cl-toolbar">
        <label className="cl-search">
          <span className="cl-sr">Search classes</span>
          <input
            type="search"
            placeholder="Search classes…"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            disabled={!ready}
          />
        </label>

        <label>
          <span className="cl-sr">Filter classes</span>
          <select
            value={filter}
            onChange={(event) => setFilter(event.target.value)}
            disabled={!ready}
          >
            <option value="all">All classes</option>
            <option value="managed">Classes I manage</option>
            <option value="member">Classes I participate in</option>
            <option value="archived">Archived classes</option>
          </select>
        </label>

        <label>
          <span className="cl-sr">Sort classes</span>
          <select
            value={sort}
            onChange={(event) => setSort(event.target.value)}
            disabled={!ready}
          >
            <option value="name">Name: A–Z</option>
            <option value="name-desc">Name: Z–A</option>
          </select>
        </label>

        <span className="cl-count" aria-live="polite">
          {ready ? `${visible.length} classes` : "— classes"}
        </span>

        <button
          type="button"
          onClick={resource.reload}
          disabled={action.busy || resource.status === "loading"}
        >
          Refresh
        </button>
      </div>

      {!ready ? (
        <ResourceMessage resource={resource} />
      ) : classes.length === 0 ? (
        <EmptyMessage title="No classes yet">
          Create a class or accept an invitation to get started.
        </EmptyMessage>
      ) : visible.length === 0 ? (
        <EmptyMessage title="No matching classes">
          Try another search or change the class filter.
        </EmptyMessage>
      ) : (
        <div className="cl-grid">
          {visible.map((item) => (
            <ClassCard key={item.id} item={item} />
          ))}
        </div>
      )}

      {import.meta.env.DEV && (
        <aside className="cl-dev-links">
          <strong>Layout review:</strong>
          <Link to="/app/classes/layout">Class dashboard</Link>
          <span>Available in development only.</span>
        </aside>
      )}
    </section>
  );
}
