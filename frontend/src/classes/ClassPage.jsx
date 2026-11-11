import QuizCard from "../authenticated-demo/QuizCard";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";
import { useAccount } from "../authenticated-demo/account";
import HostQuizButton from "../authenticated-demo/HostQuizButton";
import ConfirmDialog from "../authenticated-demo/ConfirmDialog";
import RequestError from "../authenticated-demo/RequestError";
import { useConfirm } from "../authenticated-demo/useConfirm";
import { useFileDownload } from "../authenticated-demo/useFileDownload";
import { useAction, useApi } from "../authenticated-demo/rest";
import ClassLiveButton from "./ClassLiveButton";
import {
  ADMIN_SECTIONS,
  APPROVED_SORTS,
  approvalLabel,
  canSubmitForApproval,
  copyText,
  HISTORY_VIEWS,
  MY_QUIZ_SORTS,
  quizAccessLabel,
  quizStatusLabel,
  resolveAdminSection,
  SUBMISSION_FILTERS,
  SUBMISSION_SORTS,
} from "./classHelpers";
import { EmptyMessage, ResourceMessage } from "./ClassUI";
import { ClassMembers, ClassSettings } from "./ClassManagement";
import {
  useApprovedQuizzes,
  useClassDashboard,
  useClassQuizzes,
  useClassSubmissions,
  useClassResource,
  useClassSessions,
  useMyClassQuizzes,
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
  controls = null,
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

        {controls}

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
function PresentationsTable({ classInfo, studentCount, controls }) {
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
      controls={controls}
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

function SortSelect({ label, value, choices, onChange }) {
  return (
    <label className="cl-sort">
      <span className="cl-sr">{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        {Object.entries(choices).map(([key, choice]) => (
          <option key={key} value={key}>
            {typeof choice === "string" ? choice : choice.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function Pager({ caption, pagination, onPageChange }) {
  if (!pagination || pagination.total_pages <= 1) return null;
  const { page, total_pages: totalPages } = pagination;

  return (
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
  );
}

// Approved quizzes in this class. Every active member sees them; the quiz
// owner or an organizer can host (Task 5 checks the same on the server).
function PresentTable({ classInfo }) {
  const action = useAction();
  const [page, setPage] = useState(1);
  const [sortKey, setSortKey] = useState("recent");
  const [query, setQuery] = useState("");
  const resource = useApprovedQuizzes(classInfo.id, page, sortKey);

  if (classInfo.archived) {
    return (
      <EmptyMessage title="Present">
        This class is archived, so no new sessions can start in it.
      </EmptyMessage>
    );
  }

  const pending = reportResource(resource);
  if (pending) return pending;

  const needle = query.trim().toLowerCase();
  const quizzes = resource.data.items.filter((quiz) =>
    `${quiz.title} ${quiz.author_name}`.toLowerCase().includes(needle),
  );
  const total = resource.data.pagination.total_items;

  return (
    <>
      <div className="cl-toolbar">
        <label className="cl-search">
          <span className="cl-sr">Search this page of approved quizzes</span>
          <input
            type="search"
            placeholder="Search this page of approved quizzes…"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>

        <SortSelect
          label="Sort approved quizzes"
          value={sortKey}
          choices={APPROVED_SORTS}
          onChange={(key) => {
            setSortKey(key);
            setPage(1);
          }}
        />

        <span className="cl-count" aria-live="polite">
          {total} approved {total === 1 ? "quiz" : "quizzes"}
        </span>
      </div>

      <RequestError error={action.error} />

      {quizzes.length === 0 ? (
        <EmptyMessage title={needle ? "No matches" : "No approved quizzes yet"}>
          {needle
            ? "No approved quiz matches your search."
            : "Publish a quiz, then send it for approval from My quizzes. Once an organizer approves it, it can be hosted here."}
        </EmptyMessage>
      ) : (
        <div className="qc-grid" aria-label="Approved quizzes">
          {quizzes.map((quiz) => (
            <QuizCard
              key={quiz.quiz_id}
              title={quiz.title}
              // Only people who can open the quiz page get the link.
              to={quiz.can_view ? "/app/quizzes/" + quiz.quiz_id : null}
              state={{ classId: classInfo.id }}
              status="Approved"
              headline={
                quiz.question_count +
                (quiz.question_count === 1 ? " question" : " questions")
              }
              actions={
                // Owners and organizers see the Host button, or why it's
                // blocked (e.g. "Publish changes first"). Everyone else
                // just learns who can host.
                quiz.hosting?.reason === "not_host" ? (
                  <small>Hosted by its owner or an organizer</small>
                ) : (
                  <HostQuizButton
                    quiz={quiz}
                    classId={classInfo.id}
                    action={action}
                    label="Host in this class"
                  />
                )
              }
            >
              <p>
                By {quiz.author_name} · approved {formatDate(quiz.approved_at)}
              </p>
            </QuizCard>
          ))}
        </div>
      )}

      <Pager
        caption="Approved quizzes"
        pagination={resource.data.pagination}
        onPageChange={setPage}
      />
    </>
  );
}

// Quizzes in this class the caller owns or edits as a collaborator.
function MyQuizzesTable({ classInfo, onApprovalChange }) {
  const api = useApi();
  const action = useAction();
  const [page, setPage] = useState(1);
  const [sortKey, setSortKey] = useState("recent");
  const resource = useMyClassQuizzes(classInfo.id, page, sortKey);
  const pending = reportResource(resource);
  const canSubmit =
    classInfo.membershipStatus === "ACTIVE" && !classInfo.archived;

  if (pending) return pending;

  async function submitForApproval(quiz) {
    const sent = await action.run(() =>
      api(`/classes/${classInfo.id}/quiz-submissions`, {
        method: "POST",
        body: JSON.stringify({ quiz_version_id: quiz.published_version_id }),
      }),
    );
    if (sent) {
      resource.reload();
      onApprovalChange?.();
    }
  }

  async function withdraw(quiz) {
    const done = await action.run(async () => {
      await api(
        `/classes/${classInfo.id}/quiz-submissions/${quiz.approval_submission_id}`,
        { method: "DELETE" },
      );
      return true;
    });
    if (done) {
      resource.reload();
      onApprovalChange?.();
    }
  }

  return (
    <>
    <RequestError error={action.error} />
    <ReportTable
      caption="My quizzes"
      noun="quiz"
      headers={["Quiz", "Access", "Status", "Approval", "Questions", "Last edited"]}
      emptyTitle="No quizzes yet"
      emptyText={
        classInfo.membershipStatus === "ACTIVE" && !classInfo.archived
          ? "Create a quiz with + New quiz, or ask a classmate to share one with you."
          : "Quizzes you own or that are shared with you in this class appear here."
      }
      pagination={resource.data.pagination}
      onPageChange={setPage}
      controls={
        <SortSelect
          label="Sort my quizzes"
          value={sortKey}
          choices={MY_QUIZ_SORTS}
          onChange={(key) => {
            setSortKey(key);
            setPage(1);
          }}
        />
      }
      rows={resource.data.items.map((quiz) => ({
        key: quiz.quiz_id,
        text: `${quiz.title} ${quiz.author_name}`,
        cells: [
          <Link
            to={`/app/quizzes/${quiz.quiz_id}`}
            state={{ classId: classInfo.id }}
          >
            {quiz.title}
          </Link>,
          quiz.my_access === "EDITOR"
            ? `Editor · shared by ${quiz.author_name}`
            : quizAccessLabel(quiz.my_access),
          quizStatusLabel(quiz.status),
          <span className="cl-approval">
            {quiz.status === "PUBLISHED" ? approvalLabel(quiz.approval_status) : "—"}
            {canSubmit && canSubmitForApproval(quiz) && (
              <button
                type="button"
                className="cl-secondary"
                disabled={action.busy}
                onClick={() => void submitForApproval(quiz)}
              >
                {quiz.approval_status ? "Send again" : "Send for approval"}
              </button>
            )}
            {quiz.approval_status === "PENDING" && quiz.approval_sent_by_me && (
              <button
                type="button"
                className="cl-secondary"
                disabled={action.busy}
                onClick={() => void withdraw(quiz)}
              >
                Withdraw
              </button>
            )}
          </span>,
          formatScore(quiz.question_count),
          formatDate(quiz.updated_at),
        ],
      }))}
    />
    </>
  );
}

// The organizer's approval queue (Admin view): every submission in the class,
// pending first by default. Members follow their own requests in My quizzes.
function SubmissionsTable({ classInfo, onChange }) {
  const api = useApi();
  const action = useAction();
  const [page, setPage] = useState(1);
  const [sortKey, setSortKey] = useState("oldest");
  const [status, setStatus] = useState("PENDING");
  const resource = useClassSubmissions(classInfo.id, page, sortKey, status);
  const pending = reportResource(resource);

  if (pending) return pending;

  async function act(submission, request) {
    const done = await action.run(async () => {
      await api(
        `/classes/${classInfo.id}/quiz-submissions/${submission.submission_id}`,
        request,
      );
      return true;
    });
    if (done) {
      resource.reload();
      onChange?.();
    }
  }

  const decide = (submission, decision) =>
    act(submission, {
      method: "PATCH",
      body: JSON.stringify({ status: decision }),
    });

  return (
    <>
      <RequestError error={action.error} />
      <ReportTable
        caption="Approvals"
        noun="submission"
        headers={["Quiz", "Version", "Submitted by", "Submitted", "Status", "Decision"]}
        emptyTitle={status === "PENDING" ? "Nothing to review" : "No submissions"}
        emptyText="When a member sends a published quiz for approval, it shows up here."
        pagination={resource.data.pagination}
        onPageChange={setPage}
        controls={
          <>
            <SortSelect
              label="Show submissions"
              value={status}
              choices={SUBMISSION_FILTERS}
              onChange={(value) => {
                setStatus(value);
                setPage(1);
              }}
            />
            <SortSelect
              label="Sort submissions"
              value={sortKey}
              choices={SUBMISSION_SORTS}
              onChange={(key) => {
                setSortKey(key);
                setPage(1);
              }}
            />
          </>
        }
        rows={resource.data.items.map((item) => {
          const version = `v${item.version_number} · ${item.question_count} ${
            item.question_count === 1 ? "question" : "questions"
          }${item.is_current_version ? "" : " · outdated"}`;
          const decided = item.decided_by_name
            ? ` by ${item.decided_by_name}`
            : "";
          const statusCell =
            item.status === "PENDING"
              ? approvalLabel(item.status)
              : `${approvalLabel(item.status)}${decided}`;
          const actions =
            item.status !== "PENDING" ? (
              "—"
            ) : (
              <span className="cl-approval">
                <button
                  type="button"
                  disabled={action.busy || classInfo.archived || !item.is_current_version}
                  title={
                    item.is_current_version
                      ? undefined
                      : "A newer version was published; only rejection is possible."
                  }
                  onClick={() => void decide(item, "APPROVED")}
                >
                  Approve
                </button>
                <button
                  type="button"
                  className="cl-secondary"
                  disabled={action.busy}
                  onClick={() => void decide(item, "REJECTED")}
                >
                  Reject
                </button>
              </span>
            );

          return {
            key: item.submission_id,
            text: `${item.quiz_title} ${item.submitter_name}`,
            cells: [
              <Link
                to={`/app/classes/${classInfo.id}/submissions/${item.submission_id}`}
                title="See exactly the version that was submitted"
              >
                {item.quiz_title}
              </Link>,
              version,
              item.submitter_name,
              formatDate(item.submitted_at),
              statusCell,
              actions,
            ],
          };
        })}
      />
    </>
  );
}

function ClassQuizzesTable({ classInfo, controls }) {
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
      controls={controls}
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

// Organizer view: completed presentations, listed one per session or
// grouped by quiz.
function ClassHistory({ classInfo, studentCount, view, onViewChange }) {
  const controls = (
    <div className="cl-toggle" role="group" aria-label="Group presentations">
      {Object.entries(HISTORY_VIEWS).map(([key, label]) => (
        <button
          key={key}
          type="button"
          aria-pressed={view === key}
          onClick={() => onViewChange(key)}
        >
          {label}
        </button>
      ))}
    </div>
  );

  return view === "quizzes" ? (
    <ClassQuizzesTable classInfo={classInfo} controls={controls} />
  ) : (
    <PresentationsTable
      classInfo={classInfo}
      studentCount={studentCount}
      controls={controls}
    />
  );
}

// Class settings in a modal opened from the class header.
function SettingsDialog({ classInfo, onChange, onClose }) {
  const ref = useRef(null);

  useEffect(() => {
    const dialog = ref.current;
    if (dialog && !dialog.open) dialog.showModal();
  }, []);

  return (
    <dialog
      ref={ref}
      className="cl-dialog"
      aria-labelledby="settings-heading"
      onCancel={(event) => {
        // Escape in a nested confirmation reaches here too; ignore it.
        if (event.target !== ref.current) return;
        event.preventDefault();
        onClose();
      }}
      onClick={(event) => {
        // A click on the backdrop lands on the <dialog> itself.
        if (event.target === ref.current) onClose();
      }}
    >
      <div className="cl-dialog-heading">
        <span>{classInfo.name}</span>
        <button type="button" className="cl-secondary" onClick={onClose}>
          Close
        </button>
      </div>

      <div className="cl-dialog-body">
        <ClassSettings classInfo={classInfo} onChange={onChange} />
      </div>
    </dialog>
  );
}

const USER_SECTIONS = ["My quizzes", "Present", "Participate"];

function ClassWorkspace({ classInfo, onChange }) {
  const account = useAccount();
  const [searchParams, setSearchParams] = useSearchParams();
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

  const requestedSection = searchParams.get("section");
  const startsInUserView =
    !showAdminLayout || searchParams.get("view") === "user";
  // Also maps the old Quizzes, Students and Settings tab names.
  const adminStart = resolveAdminSection(requestedSection);

  const [section, setSection] = useState(() => {
    if (startsInUserView) {
      return USER_SECTIONS.includes(requestedSection)
        ? requestedSection
        : "My quizzes";
    }
    return adminStart.section;
  });
  const [historyView, setHistoryView] = useState(adminStart.historyView);
  const [settingsOpen, setSettingsOpen] = useState(
    !startsInUserView && adminStart.settingsOpen,
  );

  function closeSettings() {
    setSettingsOpen(false);
    // Don't reopen it when the page reloads the class after a change.
    if (searchParams.get("section") === "Settings") {
      const next = new URLSearchParams(searchParams);
      next.delete("section");
      setSearchParams(next, { replace: true });
    }
  }

  const adminView = showAdminLayout && view === "admin";

  const sections = adminView ? ADMIN_SECTIONS : USER_SECTIONS;
  const pendingApprovals =
    dashboard.status === "ready" ? dashboard.data.pending_submission_count : 0;

  const activeSection = sections.includes(section) ? section : sections[0];

  function changeView(nextView) {
    setView(nextView);
    // Counts may be stale after time in the other view.
    dashboard.reload();
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

                <button
                  type="button"
                  className="cl-secondary"
                  aria-haspopup="dialog"
                  onClick={() => setSettingsOpen(true)}
                >
                  Settings
                </button>
              </>
            )}
          </div>
        )}
      </div>

      {adminView && settingsOpen && (
        <SettingsDialog
          classInfo={classInfo}
          onChange={onChange}
          onClose={closeSettings}
        />
      )}

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
              {label === "Approvals" && pendingApprovals > 0 && (
                <span className="cl-badge">
                  {pendingApprovals}
                  <span className="cl-sr"> pending</span>
                </span>
              )}
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
      ) : activeSection === "Approvals" ? (
        <SubmissionsTable
          classInfo={classInfo}
          onChange={dashboard.reload}
        />
      ) : activeSection === "My quizzes" ? (
        <MyQuizzesTable
          classInfo={classInfo}
          onApprovalChange={dashboard.reload}
        />
      ) : activeSection === "Present" ? (
        <PresentTable classInfo={classInfo} />
      ) : activeSection === "Presentations" ? (
        <ClassHistory
          classInfo={classInfo}
          studentCount={studentCount}
          view={historyView}
          onViewChange={setHistoryView}
        />
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
