import { Link } from "react-router";

import { copyText, shortName } from "./classHelpers";

export function ResourceMessage({ resource }) {
  if (resource.status === "loading") {
    return (
      <div className="cl-state" role="status">
        <h2>Loading…</h2>
        <p>Please wait while we load your class information.</p>
      </div>
    );
  }

  if (resource.status === "error") {
    return (
      <div className="cl-state" role="alert">
        <h2>Unable to load this page</h2>
        <p>
          {resource.error?.message || "Something went wrong. Please try again."}
        </p>

        {typeof resource.reload === "function" && (
          <button type="button" onClick={resource.reload}>
            Try again
          </button>
        )}
      </div>
    );
  }

  if (resource.status === "forbidden") {
    return (
      <div className="cl-state" role="alert">
        <h2>Access unavailable</h2>
        <p>You do not have permission to view this class.</p>
        <Link to="/app/classes">Back to classes</Link>
      </div>
    );
  }

  if (resource.status === "not-found") {
    return (
      <div className="cl-state">
        <h2>Class not found</h2>
        <p>This class may no longer be available.</p>
        <Link to="/app/classes">Back to classes</Link>
      </div>
    );
  }

  return (
    <div className="cl-state" role="status">
      <h2>Classes are coming soon</h2>
      <p>
        Class information is not available yet. Your existing quiz dashboard is
        still available.
      </p>
      <Link className="cl-button" to="/app/dashboard/present">
        Open quiz dashboard →
      </Link>
    </div>
  );
}

export function EmptyMessage({ title, children }) {
  return (
    <div className="cl-state">
      <h2>{title}</h2>
      <p>{children}</p>
    </div>
  );
}

export function ClassCard({ item }) {
  const managesClass = item.canManage === true;
  const href = `/app/classes/${encodeURIComponent(item.id)}`;

  return (
    <article
      className={`cl-card ${
        managesClass ? "cl-card-managed" : "cl-card-member"
      }`}
    >
      <div className="cl-card-banner">
        <span className="cl-role">{item.roleLabel || "Class member"}</span>

        <span className="cl-card-code">{shortName(item.name)}</span>
      </div>

      <div className="cl-card-body">
        <h2>
          <Link to={href}>{item.name}</Link>
        </h2>

        {item.ownerName && <p className="cl-owner">{item.ownerName}</p>}

        {managesClass && <p className="cl-owner cl-you">You run this class</p>}

        <p className="cl-muted">
          {item.archived ? "Archived class" : "Active class"}
        </p>
      </div>

      <div className="cl-card-footer">
        <Link to={href}>
          {managesClass ? "Admin view" : "Dashboard"}
          <span aria-hidden="true"> →</span>
        </Link>

        {managesClass ? (
          <details className="ui-row-menu">
            <summary aria-label={`Actions for ${item.name}`}>⋯</summary>

            <div className="ui-row-options" role="menu">
              <Link role="menuitem" to={href}>
                <span aria-hidden="true">→</span> Open admin view
              </Link>

              {item.code && (
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => copyText(item.code)}
                >
                  <span aria-hidden="true">⧉</span> Copy class code ·{" "}
                  {item.code}
                </button>
              )}
            </div>
          </details>
        ) : (
          <Link
            className="cl-card-go"
            to={href}
            aria-label={`Open ${item.name}`}
          >
            →
          </Link>
        )}
      </div>
    </article>
  );
}
