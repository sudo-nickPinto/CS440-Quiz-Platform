import { Link } from "react-router";

import { shortName } from "./classHelpers";

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

  // "ready": the caller renders the data itself.
  return null;
}

export function EmptyMessage({ title, children }) {
  return (
    <div className="cl-state">
      <h2>{title}</h2>
      <p>{children}</p>
    </div>
  );
}

// The whole card opens the class. The class name is the only link, stretched
// over the card (see .cl-card-link in classes.css), so it stays one tab stop
// with a clear name for screen readers. Class actions live inside the class.
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
          <Link className="cl-card-link" to={href}>
            {item.name}
          </Link>
        </h2>

        {item.ownerName && <p className="cl-owner">{item.ownerName}</p>}

        {managesClass && <p className="cl-owner cl-you">You run this class</p>}

        <p className="cl-muted">
          {item.archived ? "Archived class" : "Active class"}
        </p>
      </div>
    </article>
  );
}
