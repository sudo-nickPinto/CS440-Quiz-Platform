import { useState } from "react";
import { useAuth0 } from "@auth0/auth0-react";
import { Link, useNavigate, useParams } from "react-router";

import { useAccount } from "../authenticated-demo/account";
import HostQuizButton from "../authenticated-demo/HostQuizButton";
import RequestError from "../authenticated-demo/RequestError";
import { useAction, useApi, useResource } from "../authenticated-demo/rest";
import ClassLiveButton from "./ClassLiveButton";
import {
  useClassDashboard,
  useClassResource,
  useClassSessions,
  useClassStudents,
} from "./classResources";
import { EmptyMessage, ResourceMessage } from "./ClassUI";
import { ClassMembers, ClassSettings } from "./ClassManagement";

const DATE_FORMAT = new Intl.DateTimeFormat(undefined, {
  month: "short",
  day: "numeric",
  year: "numeric",
});

function formatDate(value) {
  return value ? DATE_FORMAT.format(new Date(value)) : "—";
}

function formatScore(value) {
  return value === null || value === undefined
    ? "—"
    : Number(value).toLocaleString();
}

function formatRate(value) {
  return value === null || value === undefined
    ? "—"
    : `${Math.round(value * 100)}%`;
}

function reportResource(resource) {
  return resource.status === "ready" ? null : (
    <ResourceMessage resource={resource} />
  );
}

// A searchable report table; `rows` are { key, text, cells } where `text`
// is what the search box matches.
function ReportTable({ caption, noun, headers, rows, emptyTitle, emptyText }) {
  const [query, setQuery] = useState("");
  const needle = query.trim().toLowerCase();
  const visible = rows.filter((row) =>
    row.text.toLowerCase().includes(needle),
  );
  const plural = visible.length === 1 ? noun : `${noun}s`;

  return (
    <>
      <div className="cl-toolbar">
        <label className="cl-search">
          <span className="cl-sr">Search {caption.toLowerCase()}</span>
          <input
            type="search"
            placeholder={`Search ${caption.toLowerCase()}…`}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>

        <span className="cl-count" aria-live="polite">
          {visible.length} {plural}
        </span>
      </div>

      <div className="cl-table-wrap">
        <table className="cl-table">
          <caption className="cl-sr">{caption}</caption>

          <thead>
            <tr>
              {headers.map((heading) => (
                <th key={heading} scope="col">
                  {heading}
                </th>
              ))}
            </tr>
          </thead>

          <tbody>
            {visible.length === 0 ? (
              <tr>
                <td colSpan={headers.length}>
                  <div className="cl-state" role="status">
                    <h2>{needle ? "No matches" : emptyTitle}</h2>
                    <p>{needle ? "Try another search." : emptyText}</p>
                  </div>
                </td>
              </tr>
            ) : (
              visible.map((row) => (
                <tr key={row.key}>
                  {row.cells.map((cell, index) => (
                    <td key={headers[index]}>{cell}</td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}

// Organizer view: every completed session of the class.
function PresentationsTable({ classInfo, studentCount }) {
  const account = useAccount();
  const resource = useClassSessions(classInfo.id);
  const pending = reportResource(resource);
  if (pending) return pending;

  // Session reports are open to the host and Admins only.
  const mayOpen = (session) => session.is_host || account.role === "ADMIN";

  return (
    <ReportTable
      caption="Presentations"
      noun="presentation"
      headers={[
        "Date",
        "Presentation",
        "Attendance",
        "Average",
        "Top score",
        "Results",
      ]}
      emptyTitle="No presentations yet"
      emptyText="Host a quiz in this class and it shows up here once it ends."
      rows={resource.data.items.map((session) => ({
        key: session.session_id,
        text: `${session.quiz_title} ${session.host_name}`,
        cells: [
          formatDate(session.started_at),
          session.quiz_title,
          studentCount
            ? `${session.participant_count} / ${studentCount}`
            : session.participant_count,
          formatScore(session.average_score),
          formatScore(session.top_score),
          mayOpen(session) ? (
            <Link to={`/app/results/host/${session.session_id}`}>
              Report →
            </Link>
          ) : (
            `Hosted by ${session.host_name}`
          ),
        ],
      }))}
    />
  );
}

function StudentsTable({ classInfo }) {
  const resource = useClassStudents(classInfo.id);
  const pending = reportResource(resource);
  if (pending) return pending;

  return (
    <ReportTable
      caption="Students"
      noun="student"
      headers={[
        "Rank",
        "Student",
        "Recent scores",
        "Average",
        "Attendance",
        "Total",
      ]}
      emptyTitle="No students yet"
      emptyText="Share the class code or invite members to get started."
      rows={resource.data.items.map((student, index) => ({
        key: student.account_id,
        text: `${student.display_name} ${student.email}`,
        cells: [
          student.average_score === null ? "—" : index + 1,
          <>
            <strong>{student.display_name}</strong>
            <br />
            <small>{student.email}</small>
          </>,
          student.recent_scores.length ? (
            <span
              className="cl-recent"
              aria-label={`Most recent first: ${student.recent_scores
                .map((score) => (score === null ? "absent" : score))
                .join(", ")}`}
            >
              {student.recent_scores.map((score, scoreIndex) => (
                <span key={scoreIndex} data-absent={score === null}>
                  {score === null ? "–" : formatScore(score)}
                </span>
              ))}
            </span>
          ) : (
            "—"
          ),
          formatScore(student.average_score),
          formatRate(student.attendance_rate),
          formatScore(student.total_points),
        ],
      }))}
    />
  );
}

// Member view: the class's sessions and how the caller did in each.
function ParticipateTable({ classInfo }) {
  const resource = useClassSessions(classInfo.id);
  const pending = reportResource(resource);
  if (pending) return pending;

  return (
    <ReportTable
      caption="Sessions"
      noun="session"
      headers={["Date", "Session", "Score", "Results"]}
      emptyTitle="No sessions yet"
      emptyText={
        "When an organizer hosts a quiz here, a Live button appears at " +
        "the top of this page."
      }
      rows={resource.data.items.map((session) => ({
        key: session.session_id,
        text: session.quiz_title,
        cells: [
          formatDate(session.started_at),
          session.quiz_title,
          session.my_score === null
            ? "Absent"
            : `${formatScore(session.my_score)} pts · #${session.my_rank}`,
          session.is_host ? (
            <Link to={`/app/results/host/${session.session_id}`}>Report →</Link>
          ) : session.my_score === null ? (
            "—"
          ) : (
            <Link to={`/app/results/me/${session.session_id}`}>My results →</Link>
          ),
        ],
      }))}
    />
  );
}

function ClassSummary({ dashboard }) {
  const data = dashboard.status === "ready" ? dashboard.data : null;
  const stats = [
    ["Students", data?.student_count],
    ["Presentations", data?.completed_session_count],
    ["Class average", data && formatScore(data.class_average)],
    ["Attendance", data && formatRate(data.attendance_rate)],
  ];

  return (
    <section className="cl-summary" aria-label="Class summary">
      {stats.map(([label, value]) => (
        <div className="cl-stat" key={label}>
          <span>{label}</span>
          <strong>{value ?? "—"}</strong>
        </div>
      ))}
    </section>
  );
}

// Same authenticated download as the session results page.
function useCsvDownload() {
  const { getAccessTokenSilently } = useAuth0();
  const action = useAction();

  async function download(path, fallbackName) {
    const result = await action.run(async () => {
      const token = await getAccessTokenSilently();
      const base = import.meta.env.VITE_API_BASE_URL.replace(/\/+$/, "");
      const response = await fetch(base + path, {
        headers: { Authorization: "Bearer " + token },
      });

      if (!response.ok) {
        const body = await response.json().catch(() => null);
        const error = new Error(body?.error?.message || "Export failed.");
        error.status = response.status;
        error.code = body?.error?.code;
        throw error;
      }

      const name = /filename="([^"]+)"/.exec(
        response.headers.get("Content-Disposition") || "",
      )?.[1];
      return { blob: await response.blob(), name: name || fallbackName };
    });

    if (!result) return;

    const url = URL.createObjectURL(result.blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = result.name;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  return { download, busy: action.busy, error: action.error };
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
  const api = useApi();
  const navigate = useNavigate();
  const leave = useAction();
  const csv = useCsvDownload();
  const dashboard = useClassDashboard(classInfo.id);
  const studentCount =
    dashboard.status === "ready" ? dashboard.data.student_count : null;

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

  async function leaveClass() {
    const message = `Leave ${classInfo.name}? You can rejoin with the class code.`;
    if (!window.confirm(message)) return;

    const left = await leave.run(async () => {
      await api(`/classes/${classInfo.id}/membership`, { method: "DELETE" });
      return true;
    });

    if (left) navigate("/app/classes");
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
              disabled={csv.busy}
              onClick={() =>
                void csv.download(
                  `/classes/${classInfo.id}/grades/export.csv`,
                  "class-grades.csv",
                )
              }
            >
              {csv.busy ? "Preparing…" : "Export grades"}
            </button>
          </div>
        )}
      </div>

      <ClassLiveButton classId={classInfo.id} />

      {classInfo.archived && (
        <p className="cl-section-note">This class is archived.</p>
      )}

      <RequestError error={csv.error || leave.error} />

      {adminView && <ClassSummary dashboard={dashboard} />}

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
            {classInfo.canManage && (
              <Link className="cl-button" to="/app/quizzes/new">
                + New quiz
              </Link>
            )}

            {classInfo.membershipStatus === "ACTIVE" && (
              <button
                type="button"
                className="cl-secondary"
                disabled={leave.busy}
                onClick={() => void leaveClass()}
              >
                Leave class
              </button>
            )}
          </div>
        )}
      </div>

      {activeSection === "Members" ? (
        <ClassMembers classInfo={classInfo} onChange={onChange} />
      ) : activeSection === "Settings" ? (
        <ClassSettings classInfo={classInfo} onChange={onChange} />
      ) : activeSection === "Present" ? (
        <PresentTable classInfo={classInfo} />
      ) : activeSection === "Presentations" ? (
        <PresentationsTable classInfo={classInfo} studentCount={studentCount} />
      ) : activeSection === "Students" ? (
        <StudentsTable classInfo={classInfo} />
      ) : (
        <ParticipateTable classInfo={classInfo} />
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
      onChange={resource.reload}
    />
  );
}
