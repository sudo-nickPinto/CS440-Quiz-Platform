import { useState } from "react";
import { Link, useParams } from "react-router";

import { useAccount } from "../authenticated-demo/account";
import HostQuizButton from "../authenticated-demo/HostQuizButton";
import RequestError from "../authenticated-demo/RequestError";
import { useAction, useResource } from "../authenticated-demo/rest";
import ClassLiveButton from "./ClassLiveButton";
import { useClassResource } from "./classResources";
import { EmptyMessage, ResourceMessage } from "./ClassUI";
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

// Quizzes the caller wrote and may host as a session of this class.
function PresentTable({ classInfo }) {
  const account = useAccount();
  const action = useAction();
  const resource = useResource(classInfo.canManage ? "/quizzes" : null);
  const [query, setQuery] = useState("");

  if (!classInfo.canManage) {
    return (
      <EmptyMessage title="Present">
        Only organizers of this class can host its sessions. When one starts,
        a Live button appears at the top of this page.
      </EmptyMessage>
    );
  }

  if (classInfo.archived) {
    return (
      <EmptyMessage title="Present">
        This class is archived, so no new sessions can start in it.
      </EmptyMessage>
    );
  }

  if (resource.loading) {
    return <ResourceMessage resource={{ status: "loading" }} />;
  }

  if (resource.error) {
    return (
      <ResourceMessage
        resource={{
          status: "error",
          error: resource.error,
          reload: resource.reload,
        }}
      />
    );
  }

  const needle = query.trim().toLowerCase();
  const quizzes = (resource.data || []).filter(
    (quiz) =>
      quiz.author_id === account.account_id &&
      quiz.status === "PUBLISHED" &&
      quiz.title.toLowerCase().includes(needle),
  );

  return (
    <>
      <div className="cl-toolbar">
        <label className="cl-search">
          <span className="cl-sr">Search quizzes</span>
          <input
            type="search"
            placeholder="Search quizzes…"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>

        <span className="cl-count" aria-live="polite">
          {quizzes.length} {quizzes.length === 1 ? "quiz" : "quizzes"}
        </span>
      </div>

      <RequestError error={action.error} />

      <div className="cl-table-wrap">
        <table className="cl-table">
          <caption className="cl-sr">Quizzes you can host</caption>
          <thead>
            <tr>
              <th scope="col">Quiz</th>
              <th scope="col">Questions</th>
              <th scope="col">Actions</th>
            </tr>
          </thead>
          <tbody>
            {quizzes.length === 0 ? (
              <tr>
                <td colSpan={3}>
                  <div className="cl-state" role="status">
                    <h2>No quizzes to host</h2>
                    <p>
                      {needle
                        ? "No published quiz matches your search."
                        : "Publish a quiz to host it in this class."}
                    </p>
                  </div>
                </td>
              </tr>
            ) : (
              quizzes.map((quiz) => (
                <tr key={quiz.quiz_id}>
                  <td>
                    <Link to={`/app/quizzes/${quiz.quiz_id}`}>{quiz.title}</Link>
                  </td>
                  <td>{quiz.question_count}</td>
                  <td>
                    <HostQuizButton
                      quiz={quiz}
                      action={action}
                      classId={classInfo.id}
                      label="Host in this class"
                    />
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}

function ClassWorkspace({ classInfo, onChange }) {
  const showAdminLayout = classInfo.canManage === true;

  const [view, setView] = useState(showAdminLayout ? "admin" : "user");

  const [section, setSection] = useState(
    showAdminLayout ? "Presentations" : "Present",
  );

  const adminView = showAdminLayout && view === "admin";

  const sections = adminView
    ? ["Presentations", "Students", "Members", "Settings"]
    : ["Present", "Participate"];

  const activeSection = sections.includes(section) ? section : sections[0];

  function changeView(nextView) {
    setView(nextView);
    setSection(nextView === "admin" ? "Presentations" : "Present");
  }

  return (
    <section className="cl-page" aria-labelledby="class-heading">
      <div className="cl-classbar">
        <Link className="cl-button cl-secondary" to="/app/classes">
          ← Classes
        </Link>

        <div className="cl-class-title">
          <p className="cl-eyebrow">{classInfo.roleLabel || "Class"}</p>

          <h1 id="class-heading">{classInfo.name}</h1>
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
              disabled={classInfo.archived}
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

      <ClassLiveButton classId={classInfo.id} />

      <p id="class-actions-note" className="cl-section-note">
        {classInfo.archived
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

        {!adminView && classInfo.canManage && (
          <div className="cl-actions">
            <Link className="cl-button" to="/app/quizzes/new">
              + New quiz
            </Link>
          </div>
        )}
      </div>

      {activeSection === "Members" ? (
        <ClassMembers classInfo={classInfo} onChange={onChange} />
      ) : activeSection === "Settings" ? (
        <ClassSettings classInfo={classInfo} onChange={onChange} />
      ) : activeSection === "Present" ? (
        <PresentTable classInfo={classInfo} />
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
