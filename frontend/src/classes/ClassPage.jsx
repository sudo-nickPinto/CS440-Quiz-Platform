import { useRef, useState } from "react";
import { Link, useParams } from "react-router";

import { useClassResource } from "./classResources";
import { ResourceMessage } from "./ClassUI";

const SECTION_LAYOUTS = {
  Presentations: {
    headers: [
      "Date",
      "Presentation",
      "Attendance",
      "Average",
      "Top score",
      "Results",
    ],
    message: "Presentation history is not available yet.",
  },
  Students: {
    headers: [
      "Rank",
      "Student",
      "Recent scores",
      "Average",
      "Attendance",
      "Details",
    ],
    message: "Class membership and student reports are not available yet.",
  },
  Present: {
    headers: ["Status", "Quiz", "Questions", "Actions"],
    message: "Quizzes for this class are not available yet.",
  },
  Participate: {
    headers: ["Date", "Session", "Score", "Results"],
    message: "Class sessions and participation history are not available yet.",
  },
};

function UnavailableTable({ section }) {
  const layout = SECTION_LAYOUTS[section];

  return (
    <div className="cl-table-wrap">
      <table className="cl-table">
        <caption className="cl-sr">{section}</caption>

        <thead>
          <tr>
            {layout.headers.map((heading) => (
              <th key={heading} scope="col">
                {heading}
              </th>
            ))}
          </tr>
        </thead>

        <tbody>
          <tr>
            <td colSpan={layout.headers.length}>
              <div className="cl-state" role="status">
                <h2>{section}</h2>
                <p>{layout.message}</p>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}

function ClassWorkspace({ classInfo = null, layoutOnly = false }) {
  const canManage = classInfo?.canManage === true;

  // Layout review contains no class record or student data.
  // This flag controls only the development design-review screen.
  const showAdminLayout = layoutOnly || canManage;

  const [view, setView] = useState(
    showAdminLayout ? "admin" : "user",
  );

  const [section, setSection] = useState(
    showAdminLayout ? "Presentations" : "Present",
  );

  const [joinOpen, setJoinOpen] = useState(false);
  const memberDialog = useRef(null);

  const adminView = showAdminLayout && view === "admin";

  const sections = adminView
    ? ["Presentations", "Students"]
    : ["Present", "Participate"];

  const activeSection = sections.includes(section)
    ? section
    : sections[0];

  function changeView(nextView) {
    setView(nextView);
    setSection(
      nextView === "admin" ? "Presentations" : "Present",
    );
    setJoinOpen(false);
  }

  return (
    <section className="cl-page" aria-labelledby="class-heading">
      {layoutOnly && (
        <div className="cl-review-notice">
          <strong>Development layout review.</strong>{" "}
          No class is selected. Values and actions remain unavailable.
          Switching views here does not change account permissions.
        </div>
      )}

      <div className="cl-classbar">
        <Link className="cl-button cl-secondary" to="/app/classes">
          ← Classes
        </Link>

        <div className="cl-class-title">
          <p className="cl-eyebrow">
            {layoutOnly
              ? "Class dashboard layout"
              : classInfo.roleLabel || "Class"}
          </p>

          <h1 id="class-heading">
            {layoutOnly ? "Class dashboard" : classInfo.name}
          </h1>
        </div>

        {showAdminLayout && (
          <div
            className="cl-view-switch"
            role="group"
            aria-label="Dashboard view"
          >
            <span>View</span>

            <button
              type="button"
              aria-pressed={view === "admin"}
              onClick={() => changeView("admin")}
            >
              Admin
            </button>

            <button
              type="button"
              aria-pressed={view === "user"}
              onClick={() => changeView("user")}
            >
              User
            </button>
          </div>
        )}

        {adminView && (
          <div className="cl-actions">
            <button
              type="button"
              aria-haspopup="dialog"
              onClick={() => memberDialog.current?.showModal()}
            >
              + Add member
            </button>

            <button
              type="button"
              disabled
              aria-describedby="class-actions-note"
            >
              Export grades
            </button>
          </div>
        )}
      </div>

      <p id="class-actions-note" className="cl-section-note">
        Class changes, grades, and downloads are not available yet.
      </p>

      {adminView && (
        <section className="cl-summary" aria-label="Class summary">
          {[
            "Students",
            "Presentations",
            "Class average",
            "Attendance",
          ].map((label) => (
            <div className="cl-stat" key={label}>
              <span>{label}</span>
              <strong aria-label="Not available">—</strong>
            </div>
          ))}
        </section>
      )}

      <div className="cl-section-tabs">
        <div role="group" aria-label="Class sections">
          {sections.map((label) => (
            <button
              key={label}
              type="button"
              aria-pressed={activeSection === label}
              onClick={() => setSection(label)}
            >
              {label}
            </button>
          ))}
        </div>

        {!adminView && (
          <div className="cl-actions">
            <button
              type="button"
              disabled
              aria-describedby="class-quiz-note"
            >
              + New quiz
            </button>

            <button
              type="button"
              aria-expanded={joinOpen}
              aria-controls="class-session-panel"
              onClick={() => setJoinOpen((current) => !current)}
            >
              Join
            </button>
          </div>
        )}
      </div>

      {!adminView && (
        <p id="class-quiz-note" className="cl-section-note">
          Creating and joining quizzes within a class will be available
          when class-based quizzes and sessions are connected.
        </p>
      )}

      {!adminView && joinOpen && (
        <section
          id="class-session-panel"
          className="cl-inline-panel"
          aria-labelledby="class-session-heading"
        >
          <h2 id="class-session-heading">Join a live session</h2>

          <label>
            Six-digit session code
            <input
              type="text"
              inputMode="numeric"
              maxLength={6}
              disabled
              aria-describedby="class-session-note"
            />
          </label>

          <button type="button" disabled>
            Join session →
          </button>

          <p id="class-session-note">
            Joining a session within this class is not available yet.
          </p>
        </section>
      )}

      <div className="cl-toolbar">
        <label className="cl-search">
          <span className="cl-sr">
            Search {activeSection.toLowerCase()}
          </span>

          <input
            type="search"
            placeholder={`Search ${activeSection.toLowerCase()}…`}
            disabled
          />
        </label>

        <span className="cl-count">— records</span>
      </div>

      <UnavailableTable section={activeSection} />

      <div className="cl-existing-flow">
        <p>
          Your existing quiz dashboard remains available separately
          while class features are being connected.
        </p>

        <Link className="cl-button" to="/app/dashboard/present">
          Open quiz dashboard →
        </Link>
      </div>

      {showAdminLayout && (
        <dialog
          ref={memberDialog}
          className="cl-dialog"
          aria-labelledby="member-dialog-heading"
          aria-describedby="member-dialog-note"
        >
          <div className="cl-dialog-heading">
            <h2 id="member-dialog-heading">Add a member</h2>

            <button
              type="button"
              aria-label="Close add member"
              onClick={() => memberDialog.current?.close()}
            >
              ×
            </button>
          </div>

          <div className="cl-dialog-body">
            <p id="member-dialog-note">
              Adding existing users by email is not available yet.
              No changes will be saved.
            </p>

            <label>
              Account email
              <input type="email" disabled />
            </label>

            <button type="button" disabled>
              Add member
            </button>
          </div>

          <form method="dialog" className="cl-dialog-footer">
            <button type="submit">Close</button>
          </form>
        </dialog>
      )}
    </section>
  );
}

export default function ClassPage() {
  const { classId } = useParams();
  const resource = useClassResource(classId);

  if (resource.status !== "ready") {
    return (
      <section className="cl-page">
        <div className="cl-classbar">
          <Link className="cl-button cl-secondary" to="/app/classes">
            ← Classes
          </Link>
        </div>

        <ResourceMessage resource={resource} />
      </section>
    );
  }

  if (!resource.data?.name) {
    return (
      <ResourceMessage
        resource={{
          status: "error",
          error: new Error("The class details could not be read."),
          reload: resource.reload,
        }}
      />
    );
  }

  return (
    <ClassWorkspace
      key={classId}
      classInfo={resource.data}
    />
  );
}

export function ClassLayoutReview() {
  return <ClassWorkspace layoutOnly />;
}
