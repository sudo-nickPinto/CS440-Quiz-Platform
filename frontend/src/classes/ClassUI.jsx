import { Link } from "react-router";

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

export function ClassCard({ item }) {
  const managesClass = item.canManage === true;

  return (
    <article
      className={`cl-card ${
        managesClass ? "cl-card-managed" : "cl-card-member"
      }`}
    >
      <div className="cl-card-banner">
        <span className="cl-role">{item.roleLabel || "Class member"}</span>

        <span className="cl-card-code">{item.code || "Class"}</span>
      </div>

      <div className="cl-card-body">
        <h2>
          <Link to={`/app/classes/${encodeURIComponent(item.id)}`}>
            {item.name}
          </Link>
        </h2>

        {item.ownerName && <p className="cl-owner">{item.ownerName}</p>}

        <p className="cl-muted">
          {item.archived ? "Archived class" : "Active class"}
        </p>
      </div>

      <div className="cl-card-footer">
        <Link to={`/app/classes/${encodeURIComponent(item.id)}`}>
          {managesClass ? "Manage class" : "Open class"}
          <span aria-hidden="true"> →</span>
        </Link>
      </div>
    </article>
  );
}
