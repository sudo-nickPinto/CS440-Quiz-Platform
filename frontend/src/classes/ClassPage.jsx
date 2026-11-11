import { useState } from "react";
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
import { AddMemberDialog, ClassStudents } from "./ClassManagement";
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
  columnClasses = [],
  tableClass = "",
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
            : totalItems === 0
              ? `0 ${nounLabel}`
              : `${firstItem}–${lastItem} of ${totalItems} ${nounLabel}`}
        </span>
      </div>

      <div className="cl-table-wrap">
        <table className={`cl-table ${tableClass}`.trim()}>
          <caption className="cl-sr">{caption}</caption>

          <thead>
            <tr>
              {headers.map((heading, index) => (
                <th
                  key={heading || index}
                  scope="col"
                  className={columnClasses[index] || undefined}
                >
                  {heading || <span className="cl-sr">Actions</span>}
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
                    <td
                      key={headers[index] || index}
                      className={
                        [index === 0 ? row.leadClass : "", columnClasses[index]]
                          .filter(Boolean)
                          .join(" ") || undefined
                      }
                    >
                      {cell}
                    </td>
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

const MONTH = new Intl.DateTimeFormat(undefined, { month: "short" });

// The apricot date block that leads each presentation row.
function DateBlock({ value }) {
  if (!value) return "—";
  const date = new Date(value);
  return (
    <span className="cl-date-block">
      <small>{MONTH.format(date)}</small>
      <b>{String(date.getDate()).padStart(2, "0")}</b>
    </span>
  );
}

// A navy bar for an average against the best score, with the number.
function ScoreMeter({ value, max, label }) {
  const share =
    value === null || value === undefined || !max ? 0 : Math.min(value / max, 1);
  return (
    <span className="cl-meter-cell">
      <span className="cl-meter" aria-hidden="true">
        <i style={{ width: `${Math.round(share * 100)}%` }} />
      </span>
      <b className="cl-meter-num" aria-label={label}>
        {formatScore(value == null ? value : Math.round(value))}
      </b>
    </span>
  );
}

function Fraction({ value, total }) {
  return (
    <span className="cl-fraction">
      <b>{formatScore(value)}</b>
      {total ? <small> / {formatScore(total)}</small> : null}
    </span>
  );
}

function GoLink({ to, label }) {
  return (
    <Link className="cl-go" to={to} aria-label={label} title={label}>
      →
    </Link>
  );
}

const PRESENTATION_COLUMNS = ["", "", "cl-num", "", "cl-top-col", "cl-go-cell"];

// Organizer view: every completed session of the class, styled after the
// Presentations list in class-admin-main.html.
function PresentationsTable({ classInfo, studentCount, controls }) {
  const [page, setPage] = useState(1);
  const resource = useClassSessions(classInfo.id, page);
  const pending = reportResource(resource);
  if (pending) return pending;

  const { items, pagination } = resource.data;
  const firstIndex = (pagination.page - 1) * pagination.page_size;

  return (
    <ReportTable
      caption="Presentations"
      noun="presentation"
      tableClass="cl-rows"
      columnClasses={PRESENTATION_COLUMNS}
      headers={["Date", "Presentation", "Attended", "Avg score", "Top score", ""]}
      emptyTitle="No presentations yet"
      emptyText="Host a quiz in this class and it shows up here once it ends."
      controls={controls}
      pagination={pagination}
      onPageChange={setPage}
      rows={items.map((session, index) => {
        const report = `/app/classes/${classInfo.id}/sessions/${session.session_id}/report`;
        return {
          key: session.session_id,
          text: `${session.quiz_title} ${session.host_name}`,
          leadClass: "cl-date",
          cells: [
            <DateBlock value={session.started_at} />,
            <span className="cl-quiz-cell">
              <Link className="cl-quiz-name" to={report}>
                {session.quiz_title}
              </Link>
              <small>
                P{pagination.total_items - firstIndex - index} · hosted by{" "}
                {session.host_name}
              </small>
            </span>,
            <Fraction value={session.participant_count} total={studentCount} />,
            <ScoreMeter
              value={session.average_score}
              max={session.top_score}
              label={`Average ${formatScore(session.average_score)} points`}
            />,
            <span className="cl-top-cell">
              <b>{formatScore(session.top_score)}</b>
              <small>top points</small>
            </span>,
            <GoLink to={report} label={`Results for ${session.quiz_title}`} />,
          ],
        };
      })}
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

// Approved quizzes in this class. Every active member sees them; the quiz
// owner or an organizer can host (Task 5 checks the same on the server).
function PresentTable({ classInfo }) {
  const action = useAction();
  const [page, setPage] = useState(1);
  const [sortKey, setSortKey] = useState("recent");
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

  return (
    <>
      <RequestError error={action.error} />
      <ReportTable
        caption="Approved quizzes"
        noun="quiz"
        headers={["Status", "Quiz", "Qs", "Approved", ""]}
        emptyTitle="No approved quizzes yet"
        emptyText="Publish a quiz, then send it for approval from My quizzes. Once an organizer approves it, it can be hosted here."
        pagination={resource.data.pagination}
        onPageChange={setPage}
        controls={
          <SortSelect
            label="Sort approved quizzes"
            value={sortKey}
            choices={APPROVED_SORTS}
            onChange={(key) => {
              setSortKey(key);
              setPage(1);
            }}
          />
        }
        rows={resource.data.items.map((quiz) => ({
          key: quiz.quiz_id,
          text: `${quiz.title} ${quiz.author_name}`,
          leadClass: "cl-status is-approved",
          cells: [
            "Approved",
            <span className="cl-quiz-cell">
              {/* Only people who can open the quiz page get the link. */}
              {quiz.can_view ? (
                <Link
                  className="cl-quiz-name"
                  to={`/app/quizzes/${quiz.quiz_id}`}
                  state={{ classId: classInfo.id }}
                >
                  {quiz.title}
                </Link>
              ) : (
                <strong className="cl-quiz-name">{quiz.title}</strong>
              )}
              <small>By {quiz.author_name}</small>
            </span>,
            formatScore(quiz.question_count),
            formatDate(quiz.approved_at),
            // Owners and organizers see the Host button, or why it's blocked
            // (e.g. "Publish changes first"). Everyone else learns who can.
            quiz.hosting?.reason === "not_host" ? (
              <small>Hosted by its owner or an organizer</small>
            ) : (
              <HostQuizButton
                quiz={quiz}
                classId={classInfo.id}
                action={action}
                label="Host"
              />
            ),
          ],
        }))}
      />
    </>
  );
}

// Quizzes in this class the caller owns or edits as a collaborator.
function MyQuizzesTable({ classInfo, onApprovalChange }) {
  const api = useApi();
  const action = useAction();
  const confirmer = useConfirm();
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

  // Moved here from the old global dashboard. Only the owner can archive.
  async function archive(quiz) {
    const sure = await confirmer.confirm({
      label: "Archive quiz",
      title: `Archive “${quiz.title}”?`,
      message: "It will no longer be available to host.",
      confirmLabel: "Archive quiz",
      cancelLabel: "Keep it",
    });
    if (!sure) return;
    const done = await action.run(async () => {
      await api(`/quizzes/${quiz.quiz_id}/archive`, { method: "PATCH" });
      return true;
    });
    if (done) {
      resource.reload();
      onApprovalChange?.();
    }
  }

  return (
    <>
    <ConfirmDialog confirmer={confirmer} />
    <RequestError error={action.error} />
    <ReportTable
      caption="My quizzes"
      noun="quiz"
      headers={["Status", "Quiz", "Access", "Approval", "Qs", "Edited", "Manage"]}
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
        leadClass: `cl-status is-${String(quiz.status).toLowerCase()}`,
        cells: [
          quizStatusLabel(quiz.status),
          <Link
            className="cl-quiz-name"
            to={`/app/quizzes/${quiz.quiz_id}`}
            state={{ classId: classInfo.id }}
          >
            {quiz.title}
          </Link>,
          quiz.my_access === "EDITOR"
            ? `Editor · shared by ${quiz.author_name}`
            : quizAccessLabel(quiz.my_access),
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
          quiz.my_access === "OWNER" && quiz.status !== "ARCHIVED" ? (
            <button
              type="button"
              className="cl-secondary cl-danger-text"
              disabled={action.busy}
              aria-label={`Archive ${quiz.title}`}
              onClick={() => void archive(quiz)}
            >
              Archive
            </button>
          ) : (
            "—"
          ),
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

// The same rows, grouped by quiz: when it was last presented, how often,
// and how the class did across those presentations.
function ClassQuizzesTable({ classInfo, controls }) {
  const [page, setPage] = useState(1);
  const resource = useClassQuizzes(classInfo.id, page);
  const pending = reportResource(resource);

  if (pending) return pending;

  const best = Math.max(
    0,
    ...resource.data.items.map((quiz) => quiz.average_score ?? 0),
  );

  return (
    <ReportTable
      caption="Presented quizzes"
      noun="quiz"
      tableClass="cl-rows"
      columnClasses={["", "", "cl-num", "", "cl-go-cell"]}
      headers={["Last", "Quiz", "Players", "Avg score", ""]}
      emptyTitle="No presented quizzes yet"
      emptyText="Quizzes appear here after a session in this class completes."
      controls={controls}
      pagination={resource.data.pagination}
      onPageChange={setPage}
      rows={resource.data.items.map((quiz) => {
        const report = `/app/classes/${classInfo.id}/quizzes/${quiz.quiz_id}/report`;
        return {
          key: quiz.quiz_id,
          text: quiz.title,
          leadClass: "cl-date",
          cells: [
            <DateBlock value={quiz.presented_at} />,
            <span className="cl-quiz-cell">
              <Link className="cl-quiz-name" to={report}>
                {quiz.title}
              </Link>
              <small>
                Presented {quiz.session_count}{" "}
                {quiz.session_count === 1 ? "time" : "times"}
              </small>
            </span>,
            <Fraction value={quiz.participant_count} />,
            <ScoreMeter
              value={quiz.average_score}
              max={best}
              label={`Average ${formatScore(quiz.average_score)} points`}
            />,
            <GoLink to={report} label={`Report for ${quiz.title}`} />,
          ],
        };
      })}
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

const USER_SECTIONS = ["My quizzes", "Present", "Participate"];

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
  const [addOpen, setAddOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const [nameDraft, setNameDraft] = useState(classInfo.name);
  const manage = useAction();

  async function saveName(event) {
    event.preventDefault();
    const name = nameDraft.trim();
    if (!name) return;
    if (name === classInfo.name) {
      setEditing(false);
      return;
    }
    const saved = await manage.run(async () => {
      await api(`/classes/${classInfo.id}`, {
        method: "PATCH",
        body: JSON.stringify({ name }),
      });
      return true;
    });
    if (saved) onChange();
  }

  async function archiveClass() {
    const confirmed = await confirmer.confirm({
      label: "Archive class",
      title: `Archive ${classInfo.name}?`,
      message:
        "The class code stops working and no new sessions can start. " +
        "Reports stay available. There is no restore action yet.",
      confirmLabel: "Archive class",
    });
    if (!confirmed) return;

    const archived = await manage.run(async () => {
      await api(`/classes/${classInfo.id}/archive`, { method: "POST" });
      return true;
    });
    if (archived) onChange();
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
    setSection(nextView === "admin" ? "Students" : "Present");
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

          {editing ? (
            <form className="cl-rename" onSubmit={saveName}>
              <label>
                <span className="cl-sr">Class name</span>
                <input
                  type="text"
                  value={nameDraft}
                  maxLength={100}
                  required
                  autoFocus
                  disabled={manage.busy}
                  onChange={(event) => setNameDraft(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Escape") {
                      setNameDraft(classInfo.name);
                      setEditing(false);
                    }
                  }}
                />
              </label>
              <button type="submit" disabled={manage.busy || !nameDraft.trim()}>
                Save
              </button>
              <button
                type="button"
                className="cl-secondary"
                disabled={manage.busy}
                onClick={() => {
                  setNameDraft(classInfo.name);
                  setEditing(false);
                }}
              >
                Cancel
              </button>
            </form>
          ) : (
            <div className="cl-title-row">
              <h1 id="class-heading">{classInfo.name}</h1>
              {adminView && !classInfo.archived && (
                <button
                  type="button"
                  className="cl-edit-name"
                  aria-label={`Edit class name ${classInfo.name}`}
                  title="Edit class name"
                  onClick={() => setEditing(true)}
                >
                  ✎ Edit
                </button>
              )}
            </div>
          )}
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
                  className="cl-secondary"
                  aria-haspopup="dialog"
                  disabled={classInfo.archived}
                  onClick={() => setAddOpen(true)}
                >
                  + Add member
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

                {!classInfo.archived && (
                  <button
                    type="button"
                    className="cl-secondary cl-danger"
                    disabled={manage.busy}
                    onClick={() => void archiveClass()}
                  >
                    Archive
                  </button>
                )}
              </>
            )}
          </div>
        )}
      </div>

      {adminView && addOpen && (
        <AddMemberDialog
          classInfo={classInfo}
          onClose={() => setAddOpen(false)}
        />
      )}

      <ClassLiveButton classId={classInfo.id} />

      {classInfo.archived && (
        <p className="cl-section-note">This class is archived.</p>
      )}

      <RequestError error={csv.error || leave.error || manage.error} />

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

      {activeSection === "Students" ? (
        <ClassStudents
          classInfo={classInfo}
          dashboard={dashboard}
          onChange={onChange}
        />
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
