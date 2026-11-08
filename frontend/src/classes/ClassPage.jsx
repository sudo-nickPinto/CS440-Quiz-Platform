import { useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";
import { useAccount } from "../authenticated-demo/account";
import HostQuizButton from "../authenticated-demo/HostQuizButton";
import ConfirmDialog from "../authenticated-demo/ConfirmDialog";
import RequestError from "../authenticated-demo/RequestError";
import { useConfirm } from "../authenticated-demo/useConfirm";
import { useFileDownload } from "../authenticated-demo/useFileDownload";
import { useAction, useApi, useResource } from "../authenticated-demo/rest";
import ClassLiveButton from "./ClassLiveButton";
import { copyText } from "./classHelpers";
import { EmptyMessage, ResourceMessage } from "./ClassUI";
import { ClassMembers, ClassSettings } from "./ClassManagement";
import {
  useClassDashboard,
  useClassQuizzes,
  useClassResource,
  useClassSessions,
  useClassStudents,
} from "./classResources";

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
function ReportTable({
  caption,
  noun,
  headers,
  rows,
  pagination,
  onPageChange,
  emptyTitle,
  emptyText,
}) {
  const [query, setQuery] = useState("");
  const needle = query.trim().toLowerCase();
  const visible = rows.filter((row) => row.text.toLowerCase().includes(needle));
  const totalItems = pagination?.total_items ?? rows.length;
  const page = pagination?.page ?? 1;
  const totalPages = pagination?.total_pages ?? (totalItems ? 1 : 0);
  const pageSize = pagination?.page_size ?? Math.max(rows.length, 1);
  const firstItem = totalItems === 0 ? 0 : (page - 1) * pageSize + 1;
  const lastItem = Math.min(firstItem + rows.length - 1, totalItems);
  const nounLabel = totalItems === 1 ? noun : `${noun}s`;

  return (
    <>
      <div className="cl-toolbar">
        <label className="cl-search">
          <span className="cl-sr">
            Search this page of {caption.toLowerCase()}
          </span>
          <input
            type="search"
            placeholder={`Search this page of ${caption.toLowerCase()}…`}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>

        <span className="cl-count" aria-live="polite">
          {needle
            ? `${visible.length} of ${rows.length} ${nounLabel} on this page`
            : `${firstItem}–${lastItem} of ${totalItems} ${nounLabel}`}
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

      {onPageChange && totalPages > 1 && (
        <nav className="cl-pagination" aria-label={`${caption} pages`}>
          <button
            type="button"
            disabled={page <= 1}
            onClick={() => onPageChange(page - 1)}
          >
            ← Previous
          </button>
          <span>
            Page {page} of {totalPages}
          </span>
          <button
            type="button"
            disabled={page >= totalPages}
            onClick={() => onPageChange(page + 1)}
          >
            Next →
          </button>
        </nav>
      )}
    </>
  );
}

// Organizer view: every completed session of the class.
function PresentationsTable({ classInfo, studentCount }) {
  const [page, setPage] = useState(1);
  const resource = useClassSessions(classInfo.id, page);
  const pending = reportResource(resource);
  if (pending) return pending;

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
      pagination={resource.data.pagination}
      onPageChange={setPage}
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
          <Link
            to={`/app/classes/${classInfo.id}/sessions/${session.session_id}/report`}
          >
            Report →
          </Link>,
        ],
      }))}
    />
  );
}

function StudentsTable({ classInfo }) {
  const [page, setPage] = useState(1);
  const resource = useClassStudents(classInfo.id, page);
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
      pagination={resource.data.pagination}
      onPageChange={setPage}
      rows={resource.data.items.map((student, index) => ({
        key: student.account_id,
        text: `${student.display_name} ${student.email}`,
        cells: [
          student.average_score === null
            ? "—"
            : (resource.data.pagination.page - 1) *
                resource.data.pagination.page_size +
              index +
              1,
          <>
            <Link
              to={`/app/classes/${classInfo.id}/students/${student.account_id}/report`}
            >
              <strong>{student.display_name}</strong>
            </Link>
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
  const [page, setPage] = useState(1);
  const resource = useClassSessions(classInfo.id, page);
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
      pagination={resource.data.pagination}
      onPageChange={setPage}
      rows={resource.data.items.map((session) => ({
        key: session.session_id,
        text: session.quiz_title,
        cells: [
          formatDate(session.started_at),
          session.quiz_title,
          session.my_score === null
            ? "Absent"
            : `${formatScore(session.my_score)} pts · #${session.my_rank}`,
          classInfo.canManage || session.my_score != null ? (
            <Link
              to={`/app/classes/${classInfo.id}/sessions/${session.session_id}/report`}
            >
              {classInfo.canManage ? "Session report →" : "My results →"}
            </Link>
          ) : (
            "—"
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

// Quizzes the caller wrote and may host as a session of this class.
function PresentTable({ classInfo }) {
  const account = useAccount();
  const action = useAction();
  const resource = useResource(classInfo.canManage ? "/quizzes" : null);
  const [query, setQuery] = useState("");

  if (!classInfo.canManage) {
    return (
      <EmptyMessage title="Present">
        Only organizers of this class can host its sessions. When one starts, a
        Live button appears at the top of this page.
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
      // GET /quizzes spans all of the caller's classes; show only this one.
      quiz.class_id === classInfo.id &&
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
                    <Link
                      to={`/app/quizzes/${quiz.quiz_id}`}
                      state={{ classId: classInfo.id }}
                    >
                      {quiz.title}
                    </Link>
                  </td>
                  <td>{quiz.question_count}</td>
                  <td>
                    <HostQuizButton
                      quiz={quiz}
                      action={action}
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

function ClassQuizzesTable({ classInfo }) {
  const [page, setPage] = useState(1);
  const resource = useClassQuizzes(classInfo.id, page);
  const pending = reportResource(resource);

  if (pending) return pending;

  return (
    <ReportTable
      caption="Presented quizzes"
      noun="quiz"
      headers={[
        "Quiz",
        "Last presented",
        "Presentations",
        "Participations",
        "Average",
        "Report",
      ]}
      emptyTitle="No presented quizzes yet"
      emptyText="Quizzes appear here after a session in this class completes."
      pagination={resource.data.pagination}
      onPageChange={setPage}
      rows={resource.data.items.map((quiz) => ({
        key: quiz.quiz_id,
        text: quiz.title,
        cells: [
          quiz.title,
          formatDate(quiz.presented_at),
          formatScore(quiz.session_count),
          formatScore(quiz.participant_count),
          formatScore(quiz.average_score),
          <Link
            to={`/app/classes/${classInfo.id}/quizzes/${quiz.quiz_id}/report`}
          >
            Report →
          </Link>,
        ],
      }))}
    />
  );
}

function ClassWorkspace({ classInfo, onChange }) {
  const account = useAccount();
  const [searchParams] = useSearchParams();
  const showAdminLayout = classInfo.canManage === true;
  const api = useApi();
  const navigate = useNavigate();
  const leave = useAction();
  const confirmer = useConfirm();
  const [copied, setCopied] = useState(false);
  const csv = useFileDownload();
  const dashboard = useClassDashboard(classInfo.id);
  const studentCount =
    dashboard.status === "ready" ? dashboard.data.student_count : null;

  const [view, setView] = useState(() => {
    if (searchParams.get("view") === "user") {
      return "user";
    }

    return showAdminLayout ? "admin" : "user";
  });

  const [section, setSection] = useState(() => {
    if (
      searchParams.get("view") === "user" &&
      searchParams.get("section") === "Present"
    ) {
      return "Present";
    }

    return showAdminLayout ? "Presentations" : "Present";
  });

  const adminView = showAdminLayout && view === "admin";

  const sections = adminView
    ? ["Presentations", "Quizzes", "Students", "Members", "Settings"]
    : ["Present", "Participate"];

  const activeSection = sections.includes(section) ? section : sections[0];

  function changeView(nextView) {
    setView(nextView);
    setSection(nextView === "admin" ? "Presentations" : "Present");
  }

  async function copyCode() {
    await copyText(classInfo.code);
    setCopied(true);
    setTimeout(() => setCopied(false), 1600);
  }

  async function leaveClass() {
    const confirmed = await confirmer.confirm({
      label: "Leave class",
      title: `Leave ${classInfo.name}?`,
      message: "You can rejoin with the class code.",
      confirmLabel: "Leave class",
    });
    if (!confirmed) return;

    const left = await leave.run(async () => {
      await api(`/classes/${classInfo.id}/membership`, { method: "DELETE" });
      return true;
    });

    if (left) navigate("/app/classes");
  }

  return (
    <section className="cl-page" aria-labelledby="class-heading">
      <ConfirmDialog confirmer={confirmer} />

      <div className="cl-classbar">
        <Link className="cl-button cl-secondary" to="/app/classes">
          ← Classes
        </Link>

        <div className="cl-class-title">
          <p className="cl-eyebrow">
            <span
              className={`cl-chip${
                classInfo.canManage ? "" : " cl-chip-member"
              }`}
            >
              {classInfo.roleLabel || "Class"}
            </span>

            {classInfo.canManage && classInfo.code && (
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

        {showAdminLayout && (
          <div className="cl-actions">
            {adminView && (
              <>
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
              </>
            )}
          </div>
        )}
      </div>

      <ClassLiveButton classId={classInfo.id} />

      {classInfo.archived && (
        <p className="cl-section-note">This class is archived.</p>
      )}

      <RequestError error={csv.error || leave.error} />

      {adminView &&
        (dashboard.status === "ready" ? (
          <ClassSummary dashboard={dashboard} />
        ) : (
          <ResourceMessage resource={dashboard} />
        ))}

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
            {classInfo.membershipStatus === "ACTIVE" && (
              <Link
                className="cl-button"
                to={`/app/quizzes/new?class=${classInfo.id}`}
              >
                + New quiz
              </Link>
            )}

            {classInfo.membershipStatus === "ACTIVE" && (
              <Link
                className="cl-button cl-secondary"
                to={`/app/classes/${classInfo.id}/students/${account.account_id}/report`}
              >
                My class report
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
      ) : activeSection === "Quizzes" ? (
        <ClassQuizzesTable classInfo={classInfo} />
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
