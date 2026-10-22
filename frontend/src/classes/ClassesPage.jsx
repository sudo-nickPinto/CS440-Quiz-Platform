import { useState } from "react";
import { Link } from "react-router";

import { useClassesResource } from "./classResources";
import {
  ClassCard,
  EmptyMessage,
  ResourceMessage,
} from "./ClassUI";

export default function ClassesPage() {
  const resource = useClassesResource();

  const [panel, setPanel] = useState(null);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const [sort, setSort] = useState("name");

  const ready =
    resource.status === "ready" &&
    Array.isArray(resource.data);

  const invalidResponse =
    resource.status === "ready" &&
    !Array.isArray(resource.data);

  const records = ready ? resource.data : null;

  const visible = records
    ? records
        .filter((item) =>
          item.name.toLowerCase().includes(query.trim().toLowerCase()),
        )
        .filter((item) => {
          if (filter === "managed") return item.canManage === true;
          if (filter === "member") return item.canManage === false;
          return true;
        })
        .sort((a, b) =>
          sort === "name-desc"
            ? b.name.localeCompare(a.name)
            : a.name.localeCompare(b.name),
        )
    : null;

  function togglePanel(nextPanel) {
    setPanel((current) =>
      current === nextPanel ? null : nextPanel,
    );
  }

  return (
    <section className="cl-page" aria-labelledby="classes-heading">
      <div className="cl-titlebar">
        <h1 id="classes-heading">
          Classes
          {ready && <small>{records.length} total</small>}
        </h1>

        <button
          type="button"
          className="cl-new"
          aria-expanded={panel === "create"}
          aria-controls="class-create-panel"
          onClick={() => togglePanel("create")}
        >
          <span aria-hidden="true">+</span> New class
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

      {panel === "create" && (
        <section
          id="class-create-panel"
          className="cl-inline-panel"
          aria-labelledby="create-class-heading"
        >
          <h2 id="create-class-heading">New class</h2>

          <label>
            Class name
            <input
              type="text"
              disabled
              aria-describedby="create-class-note"
            />
          </label>

          <button type="button" disabled>
            Create →
          </button>

          <p id="create-class-note">
            Creating classes is not available yet.
          </p>

          <button type="button" onClick={() => setPanel(null)}>
            Close
          </button>
        </section>
      )}

      {panel === "join" && (
        <section
          id="class-join-panel"
          className="cl-inline-panel"
          aria-labelledby="join-class-heading"
        >
          <h2 id="join-class-heading">Join a class</h2>

          <label>
            Class code
            <input
              type="text"
              disabled
              aria-describedby="join-class-note"
            />
          </label>

          <button type="button" disabled>
            Join class →
          </button>

          <p id="join-class-note">
            Joining classes by code is not available yet.
            A class code is separate from a live quiz session code.
          </p>

          <button type="button" onClick={() => setPanel(null)}>
            Close
          </button>
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
      </div>

      {invalidResponse ? (
        <ResourceMessage
          resource={{
            status: "error",
            error: new Error("The class list could not be read."),
            reload: resource.reload,
          }}
        />
      ) : !ready ? (
        <ResourceMessage resource={resource} />
      ) : records.length === 0 ? (
        <EmptyMessage title="No classes yet">
          Your classes will appear here when you create or join one.
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
          <span>These review links are available in development only.</span>
        </aside>
      )}
    </section>
  );
}
