import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";

import { useAction, useApi } from "../authenticated-demo/rest";
import RequestError from "../authenticated-demo/RequestError";
import { useClassResource } from "./classResources";
import { copyText } from "./classHelpers";
import { ResourceMessage } from "./ClassUI";
import { ClassMembers, ClassSettings } from "./ClassManagement";

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
    message: "Student grades and class reports are not available yet.",
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

function ClassWorkspace({ classInfo = null, layoutOnly = false, onChange }) {
  const canManage = classInfo?.canManage === true;

  // Layout review contains no class record or student data.
  // This flag controls only the development design-review screen.
  const showAdminLayout = layoutOnly || canManage;

  const [view, setView] = useState(showAdminLayout ? "admin" : "user");

  const [section, setSection] = useState(
    showAdminLayout ? "Presentations" : "Present",
  );

  const [joinOpen, setJoinOpen] = useState(false);
  const [code, setCode] = useState("");
  const [copied, setCopied] = useState(false);

  const api = useApi();
  const joinAction = useAction();
  const navigate = useNavigate();

  // Session codes are not tied to a class, so this is the same request as
  // the dashboard's Join strip.
  async function join(event) {
    event.preventDefault();

    if (!/^\d{6}$/.test(code)) return;

    const joined = await joinAction.run(() =>
      api("/sessions/join", {
        method: "POST",
        body: JSON.stringify({ join_code: code }),
      }),
    );

    if (joined) {
      navigate(`/app/play/${joined.session.session_id}`);
    }
  }

  async function copyCode() {
    await copyText(classInfo.code);
    setCopied(true);
    setTimeout(() => setCopied(false), 1600);
  }

  const adminView = showAdminLayout && view === "admin";

  const sections = adminView
    ? ["Presentations", "Students", "Members", "Settings"]
    : ["Present", "Participate"];

  const activeSection = sections.includes(section) ? section : sections[0];

  function changeView(nextView) {
    setView(nextView);
    setSection(nextView === "admin" ? "Presentations" : "Present");
    setJoinOpen(false);
  }

  return (
    <section className="cl-page" aria-labelledby="class-heading">
      {layoutOnly && (
        <div className="cl-review-notice">
          <strong>Development layout review.</strong> No class is selected.
          Values and actions remain unavailable. Switching views here does not
          change account permissions.
        </div>
      )}

      <div className="cl-classbar">
        <Link className="cl-button cl-secondary" to="/app/classes">
          ← Classes
        </Link>

        <div className="cl-class-title">
          <p className="cl-eyebrow">
            <span className={`cl-chip${canManage ? "" : " cl-chip-member"}`}>
              {layoutOnly
                ? "Class dashboard layout"
                : classInfo.roleLabel || "Class"}
            </span>

            {canManage && classInfo.code && (
              <button
                type="button"
                className="cl-code-chip"
                onClick={copyCode}
                aria-label={`Copy class code ${classInfo.code}`}
              >
                {copied ? "Copied" : `Code ${classInfo.code}`}
                <span aria-hidden="true"> ⧉</span>
              </button>
            )}
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
              disabled={layoutOnly || classInfo?.archived}
              onClick={() => setSection("Members")}
            >
              + Invite member
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
        {layoutOnly
          ? "This is a layout preview. Select a real class to use its features."
          : classInfo.archived
            ? "This class is archived."
            : "Class grades and grade downloads are not available yet."}
      </p>

      {adminView && (
        <section className="cl-summary" aria-label="Class summary">
          {["Students", "Presentations", "Class average", "Attendance"].map(
            (label) => (
              <div className="cl-stat" key={label}>
                <span>{label}</span>
                <strong aria-label="Not available">—</strong>
              </div>
            ),
          )}
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
            {layoutOnly ? (
              <button type="button" disabled>
                + New quiz
              </button>
            ) : (
              <Link
                className="cl-button cl-secondary"
                to="/app/quizzes/new"
                aria-describedby="class-quiz-note"
              >
                + New quiz
              </Link>
            )}

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
          Quizzes are not linked to classes yet. New quizzes and joined
          sessions appear on your main quiz dashboard.
        </p>
      )}

      {!adminView && joinOpen && (
        <form
          id="class-session-panel"
          className="ui-join-strip"
          onSubmit={join}
        >
          <label htmlFor="class-session-code">Session code</label>

          <input
            id="class-session-code"
            autoFocus
            required
            inputMode="numeric"
            autoComplete="off"
            pattern="[0-9]{6}"
            maxLength={6}
            placeholder="000000"
            value={code}
            disabled={layoutOnly || joinAction.busy}
            onChange={(event) =>
              setCode(event.target.value.replace(/\D/g, "").slice(0, 6))
            }
          />

          <button
            type="submit"
            className="qp-primary"
            disabled={layoutOnly || code.length !== 6 || joinAction.busy}
          >
            {joinAction.busy ? "Joining…" : "Go →"}
          </button>

          <RequestError error={joinAction.error} />
        </form>
      )}

      {activeSection === "Members" ? (
        layoutOnly ? (
          <div className="cl-state">
            <h2>Members</h2>
            <p>Select a real class to view and manage its members.</p>
          </div>
        ) : (
          <ClassMembers classInfo={classInfo} onChange={onChange} />
        )
      ) : activeSection === "Settings" ? (
        layoutOnly ? (
          <div className="cl-state">
            <h2>Class settings</h2>
            <p>Select a real class to change its settings.</p>
          </div>
        ) : (
          <ClassSettings classInfo={classInfo} onChange={onChange} />
        )
      ) : (
        <>
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
        </>
      )}

      <div className="cl-existing-flow">
        <p>
          Your existing quiz dashboard remains available separately while class
          features are being connected.
        </p>

        <Link className="cl-button" to="/app/dashboard/present">
          Open quiz dashboard →
        </Link>
      </div>
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
      onChange={resource.reload}
    />
  );
}

export function ClassLayoutReview() {
  return <ClassWorkspace layoutOnly />;
}
