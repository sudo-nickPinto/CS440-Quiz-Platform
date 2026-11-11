import { useEffect, useRef, useState } from "react";
import { useRemembered } from "../authenticated-demo/remember";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";
import { useAccount } from "../authenticated-demo/account";
import HostQuizButton from "../authenticated-demo/HostQuizButton";
import QuizCard from "../authenticated-demo/QuizCard";
import { hostingState, showsHostControl } from "../authenticated-demo/hosting";
import ConfirmDialog from "../authenticated-demo/ConfirmDialog";
import RequestError from "../authenticated-demo/RequestError";
import { useConfirm } from "../authenticated-demo/useConfirm";
import { useFileDownload } from "../authenticated-demo/useFileDownload";
import { useAction, useApi } from "../authenticated-demo/rest";
import ClassLiveButton from "./ClassLiveButton";
import {
  ADMIN_SECTIONS,
  approvalLabel,
  approvalButton,
  copyText,
  HISTORY_VIEWS,
  MY_QUIZ_SORTS,
  presentStatus,
  resolveAdminSection,
  resolveUserSection,
  sendForApproval,
  SUBMISSION_FILTERS,
  SUBMISSION_SORTS,
  USER_SECTIONS,
} from "./classHelpers";
import { ResourceMessage } from "./ClassUI";
import "./my-drafts.css";
import { AddMemberDialog, ClassStudents } from "./ClassManagement";
import {
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
  rememberAs = null,
}) {
  const [query, setQuery] = useRemembered(
    rememberAs && `${rememberAs}:query`,
    "",
  );
  const needle = query.trim().toLowerCase();
  const visible = rows.filter((row) => row.text.toLowerCase().includes(needle));
  const totalItems = pagination?.total_items ?? rows.length;
  const page = pagination?.page ?? 1;
  const totalPages = pagination?.total_pages ?? (totalItems ? 1 : 0);
  const pageSize = pagination?.page_size ?? Math.max(rows.length, 1);
  const firstItem = totalItems === 0 ? 0 : (page - 1) * pageSize + 1;
  const lastItem = Math.min(firstItem + rows.length - 1, totalItems);
  const nounLabel = totalItems === 1 ? noun : `${noun}s`;

  // A remembered page can be past the end once rows are removed.
  const pastEnd = Boolean(onPageChange) && page > Math.max(totalPages, 1);
  useEffect(() => {
    if (pastEnd) onPageChange(Math.max(totalPages, 1));
  }, [pastEnd, totalPages, onPageChange]);

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

// Searchable, paginated cards for quiz-browsing views. Dense grade and
// approval reports remain tables, while quizzes and personal history use the
// responsive card treatment introduced in PR #99.
function CardCollection({
  caption,
  noun,
  items,
  pagination,
  onPageChange,
  emptyTitle,
  emptyText,
  emptyAction = null,
  controls = null,
  rememberAs,
  getText,
  renderCard,
}) {
  const [query, setQuery] = useRemembered(`${rememberAs}:query`, "");
  const needle = query.trim().toLowerCase();
  const visible = items.filter((item) =>
    getText(item).toLowerCase().includes(needle),
  );
  const totalItems = pagination?.total_items ?? items.length;
  const page = pagination?.page ?? 1;
  const totalPages = pagination?.total_pages ?? (totalItems ? 1 : 0);
  const pageSize = pagination?.page_size ?? Math.max(items.length, 1);
  const firstItem = totalItems === 0 ? 0 : (page - 1) * pageSize + 1;
  const lastItem = Math.min(firstItem + items.length - 1, totalItems);
  const nounLabel = totalItems === 1 ? noun : `${noun}s`;
  const pastEnd = Boolean(onPageChange) && page > Math.max(totalPages, 1);

  useEffect(() => {
    if (pastEnd) onPageChange(Math.max(totalPages, 1));
  }, [pastEnd, totalPages, onPageChange]);

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
            ? `${visible.length} of ${items.length} ${nounLabel} on this page`
            : totalItems === 0
              ? `0 ${nounLabel}`
              : `${firstItem}–${lastItem} of ${totalItems} ${nounLabel}`}
        </span>
      </div>

      {visible.length ? (
        <div className="qc-grid" aria-label={caption}>
          {visible.map(renderCard)}
        </div>
      ) : (
        <div className="cl-state qc-empty" role="status">
          <h2>{needle ? "No matches" : emptyTitle}</h2>
          <p>{needle ? "Try another search." : emptyText}</p>
          {needle ? (
            <button type="button" onClick={() => setQuery("")}>
              Clear search
            </button>
          ) : (
            emptyAction
          )}
        </div>
      )}

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
    value === null || value === undefined || !max
      ? 0
      : Math.min(value / max, 1);
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
  const memory = `class:${classInfo.id}:presentations`;
  const [page, setPage] = useRemembered(`${memory}:page`, 1);
  const resource = useClassSessions(classInfo.id, page);
  const pending = reportResource(resource);
  if (pending) return pending;

  const { items, pagination } = resource.data;
  const firstIndex = (pagination.page - 1) * pagination.page_size;

  return (
    <ReportTable
      caption="Presentations"
      rememberAs={memory}
      noun="presentation"
      tableClass="cl-rows"
      columnClasses={PRESENTATION_COLUMNS}
      headers={[
        "Date",
        "Presentation",
        "Attended",
        "Avg score",
        "Top score",
        "",
      ]}
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

// Member view: completed and missed sessions shown as responsive quiz cards.
function ParticipateTable({ classInfo }) {
  const memory = `class:${classInfo.id}:participate`;
  const [page, setPage] = useRemembered(`${memory}:page`, 1);
  const resource = useClassSessions(classInfo.id, page);
  const pending = reportResource(resource);
  if (pending) return pending;

  // Members don't get class-wide scores, so the bar compares each score with
  // the session's top score when it's shown, otherwise with your best here.
  const best = Math.max(
    0,
    ...resource.data.items.map((session) => session.my_score ?? 0),
  );

  return (
    <CardCollection
      caption="Sessions"
      rememberAs={memory}
      noun="session"
      emptyTitle="No sessions yet"
      emptyText={
        "When an organizer hosts a quiz here, a Live button appears at " +
        "the top of this page."
      }
      pagination={resource.data.pagination}
      onPageChange={setPage}
      items={resource.data.items}
      getText={(session) => `${session.quiz_title} ${session.host_name}`}
      renderCard={(session) => {
        const played = session.my_score != null;
        const report =
          classInfo.canManage || played
            ? `/app/classes/${classInfo.id}/sessions/${session.session_id}/report`
            : null;
        const maxScore = session.top_score ?? best;
        const percentage =
          played && maxScore > 0
            ? Math.min(100, Math.max(0, (session.my_score / maxScore) * 100))
            : 0;

        return (
          <QuizCard
            key={session.session_id}
            title={session.quiz_title}
            to={report}
            status={played ? "Completed" : "Absent"}
            headline={
              played
                ? `Rank #${session.my_rank} of ${formatScore(session.participant_count)}`
                : "Did not participate"
            }
            linkLabel={classInfo.canManage ? "Session report" : "My results"}
          >
            <p>Hosted by {session.host_name}</p>
            <p>{formatDate(session.started_at)}</p>
            <p>
              <strong>
                {played
                  ? `${formatScore(session.my_score)} points`
                  : "No score recorded"}
              </strong>
            </p>
            {played && (
              <span className="qc-progress" aria-hidden="true">
                <span style={{ width: `${percentage}%` }} />
              </span>
            )}
          </QuizCard>
        );
      }}
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

// The ⋯ button and its menu. The menu is fixed to the viewport so the
// table's scroll box never clips it; it closes on outside click, Escape,
// scroll, or after picking an item.
function RowMenu({ label, children }) {
  const [place, setPlace] = useState(null);
  const wrap = useRef(null);

  useEffect(() => {
    if (!place) return undefined;
    const close = () => setPlace(null);
    const outside = (event) => {
      if (!wrap.current?.contains(event.target)) close();
    };
    const escape = (event) => {
      if (event.key === "Escape") close();
    };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    window.addEventListener("scroll", close, true);
    window.addEventListener("resize", close);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", escape);
      window.removeEventListener("scroll", close, true);
      window.removeEventListener("resize", close);
    };
  }, [place]);

  function toggle(event) {
    if (place) {
      setPlace(null);
      return;
    }
    const box = event.currentTarget.getBoundingClientRect();
    const right = document.documentElement.clientWidth - box.right;
    setPlace(
      window.innerHeight - box.bottom > 260
        ? { right, top: box.bottom + 8 }
        : { right, bottom: window.innerHeight - box.top + 8 },
    );
  }

  return (
    <div className="cl-kebab-wrap" ref={wrap}>
      <button
        type="button"
        className="cl-kebab"
        aria-haspopup="menu"
        aria-expanded={Boolean(place)}
        aria-label={label}
        title={label}
        onClick={toggle}
      >
        ⋯
      </button>
      {place && (
        <div
          className="cl-menu"
          role="menu"
          style={{ position: "fixed", ...place }}
          onClick={() => setPlace(null)}
        >
          {children}
        </div>
      )}
    </div>
  );
}

// Member view: the caller's own quizzes in this class (owned or shared with
// them). Cards retain the approval workflow and the ⋯ menu edits, hosts, or
// archives without losing the responsive treatment from PR #99.
function PresentTable({ classInfo, onApprovalChange }) {
  const api = useApi();
  const account = useAccount();
  const action = useAction();
  const confirmer = useConfirm();
  const memory = `class:${classInfo.id}:present`;
  const [page, setPage] = useRemembered(`${memory}:page`, 1);
  const [sortKey, setSortKey] = useRemembered(`${memory}:sort`, "recent", {
    isValid: (key) => key in MY_QUIZ_SORTS,
  });
  const resource = useMyClassQuizzes(classInfo.id, page, sortKey);
  const pending = reportResource(resource);
  const canSubmit =
    classInfo.membershipStatus === "ACTIVE" && !classInfo.archived;

  if (pending) return pending;

  function refresh(done) {
    if (!done) return;
    resource.reload();
    onApprovalChange?.();
  }

  async function submitForApproval(quiz) {
    refresh(await action.run(() => sendForApproval(api, classInfo.id, quiz)));
  }

  async function withdraw(quiz) {
    refresh(
      await action.run(async () => {
        await api(
          `/classes/${classInfo.id}/quiz-submissions/${quiz.approval_submission_id}`,
          { method: "DELETE" },
        );
        return true;
      }),
    );
  }

  // Only the owner can archive.
  async function archive(quiz) {
    const sure = await confirmer.confirm({
      label: "Archive quiz",
      title: `Archive “${quiz.title}”?`,
      message: "It will no longer be available to host.",
      confirmLabel: "Archive quiz",
      cancelLabel: "Keep it",
    });
    if (!sure) return;
    refresh(
      await action.run(async () => {
        await api(`/quizzes/${quiz.quiz_id}/archive`, { method: "PATCH" });
        return true;
      }),
    );
  }

  return (
    <>
      <ConfirmDialog confirmer={confirmer} />
      <RequestError error={action.error} />
      <CardCollection
        caption="My quizzes"
        rememberAs={memory}
        noun="quiz"
        emptyTitle="No quizzes yet"
        emptyText={
          canSubmit
            ? "Start a draft for this class, or ask a classmate to share one with you. Drafts stay private until you send them for approval."
            : "Quizzes you own or that are shared with you in this class appear here."
        }
        emptyAction={
          canSubmit && (
            <Link
              className="cl-button"
              to={`/app/quizzes/new?class=${classInfo.id}`}
            >
              + New quiz
            </Link>
          )
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
        items={resource.data.items}
        getText={(quiz) => `${quiz.title} ${quiz.author_name}`}
        renderCard={(quiz) => {
          const status = presentStatus(quiz);
          const owner = quiz.my_access === "OWNER";
          const archived = quiz.status === "ARCHIVED";
          const hostable =
            status.key === "approved" &&
            !classInfo.archived &&
            showsHostControl(quiz, account?.account_id) &&
            hostingState(quiz, classInfo.id).canHost;
          const button = approvalButton(quiz);
          // Send and Withdraw need an active membership in a live class.
          const clickable =
            button && !button.disabled && canSubmit && !action.busy;
          const press = () =>
            void (button.kind === "withdraw"
              ? withdraw(quiz)
              : submitForApproval(quiz));

          return (
            <QuizCard
              key={quiz.quiz_id}
              title={quiz.title}
              to={`/app/quizzes/${quiz.quiz_id}`}
              state={{ classId: classInfo.id }}
              status={status.label}
              archived={archived}
              headline={`${quiz.question_count} ${
                quiz.question_count === 1 ? "question" : "questions"
              }`}
              linkLabel="Open quiz"
              actions={
                <RowMenu label={`Actions for ${quiz.title}`}>
                  {quiz.my_access && !archived && (
                    <Link
                      role="menuitem"
                      to={`/app/quizzes/${quiz.quiz_id}/edit`}
                      state={{ classId: classInfo.id }}
                    >
                      ✎ Edit
                    </Link>
                  )}
                  <Link
                    role="menuitem"
                    to={`/app/quizzes/${quiz.quiz_id}`}
                    state={{ classId: classInfo.id }}
                  >
                    ◉ Open
                  </Link>
                  {hostable && (
                    <HostQuizButton
                      quiz={quiz}
                      classId={classInfo.id}
                      action={action}
                      label="▶ Host live"
                    />
                  )}
                  {owner && !archived && (
                    <button
                      type="button"
                      role="menuitem"
                      className="is-danger"
                      disabled={action.busy}
                      onClick={() => void archive(quiz)}
                    >
                      Archive
                    </button>
                  )}
                </RowMenu>
              }
            >
              <p>
                {owner ? (
                  <span className="cl-tag is-me">Owned by me</span>
                ) : (
                  <span className="cl-tag">Shared by {quiz.author_name}</span>
                )}
              </p>
              <p>Edited {formatDate(quiz.updated_at)}</p>
              {button && (
                <div className="qc-approval">
                  <button
                    type="button"
                    className={`cl-send is-${button.kind}`}
                    disabled={!clickable}
                    aria-disabled={button.kind === "approved" || undefined}
                    title={button.title}
                    onClick={press}
                  >
                    {button.label}
                  </button>
                  {button.note && (
                    <small className="cl-approval-note">{button.note}</small>
                  )}
                </div>
              )}
            </QuizCard>
          );
        }}
      />
    </>
  );
}

// The organizer's approval queue (Admin view): every submission in the class,
// pending first by default. Members follow their own requests in My quizzes.
function SubmissionsTable({ classInfo, onChange }) {
  const api = useApi();
  const action = useAction();
  const memory = `class:${classInfo.id}:approvals`;
  const [page, setPage] = useRemembered(`${memory}:page`, 1);
  const [sortKey, setSortKey] = useRemembered(`${memory}:sort`, "oldest", {
    isValid: (key) => key in SUBMISSION_SORTS,
  });
  const [status, setStatus] = useRemembered(`${memory}:status`, "PENDING", {
    isValid: (key) => key in SUBMISSION_FILTERS,
  });
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
        rememberAs={memory}
        noun="submission"
        headers={[
          "Quiz",
          "Version",
          "Submitted by",
          "Submitted",
          "Status",
          "Decision",
        ]}
        emptyTitle={
          status === "PENDING" ? "Nothing to review" : "No submissions"
        }
        emptyText="When a member sends a quiz for approval, it shows up here."
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
                  disabled={
                    action.busy ||
                    classInfo.archived ||
                    !item.is_current_version
                  }
                  title={
                    item.is_current_version
                      ? undefined
                      : "A newer version of this quiz exists; only rejection is possible."
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

// The same history grouped into browsable quiz cards: when each quiz was last
// presented, how often, and how the class did across those presentations.
function ClassQuizzesTable({ classInfo, controls }) {
  const memory = `class:${classInfo.id}:by-quiz`;
  const [page, setPage] = useRemembered(`${memory}:page`, 1);
  const resource = useClassQuizzes(classInfo.id, page);
  const pending = reportResource(resource);

  if (pending) return pending;

  const best = Math.max(
    0,
    ...resource.data.items.map((quiz) => quiz.average_score ?? 0),
  );

  return (
    <CardCollection
      caption="Presented quizzes"
      rememberAs={memory}
      noun="quiz"
      emptyTitle="No presented quizzes yet"
      emptyText="Quizzes appear here after a session in this class completes."
      controls={controls}
      pagination={resource.data.pagination}
      onPageChange={setPage}
      items={resource.data.items}
      getText={(quiz) => quiz.title}
      renderCard={(quiz) => {
        const report = `/app/classes/${classInfo.id}/quizzes/${quiz.quiz_id}/report`;
        const percentage =
          quiz.average_score != null && best > 0
            ? Math.min(100, Math.max(0, (quiz.average_score / best) * 100))
            : 0;
        return (
          <QuizCard
            key={quiz.quiz_id}
            title={quiz.title}
            to={report}
            status="Presented"
            headline={`${quiz.session_count} ${
              quiz.session_count === 1 ? "presentation" : "presentations"
            }`}
            linkLabel="View report"
          >
            <p>Last presented {formatDate(quiz.presented_at)}</p>
            <p>{formatScore(quiz.participant_count)} total participations</p>
            <p>
              <strong>
                Average score: {formatScore(quiz.average_score)} points
              </strong>
            </p>
            <span className="qc-progress" aria-hidden="true">
              <span style={{ width: `${percentage}%` }} />
            </span>
          </QuizCard>
        );
      }}
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

// The session-code strip under the tabs (made-dashboard-main.html): six
// digits from the host's screen, then straight into the game.
function JoinPanel() {
  const api = useApi();
  const action = useAction();
  const navigate = useNavigate();
  const [code, setCode] = useState("");

  async function join(event) {
    event.preventDefault();
    if (!/^\d{6}$/.test(code)) return;
    const joined = await action.run(() =>
      api("/sessions/join", {
        method: "POST",
        body: JSON.stringify({ join_code: code }),
      }),
    );
    if (joined) navigate(`/app/play/${joined.session.session_id}`);
  }

  return (
    <div className="cl-join-panel" id="cl-join-panel">
      <form onSubmit={join}>
        <label htmlFor="cl-join-code">Session code</label>
        <input
          id="cl-join-code"
          autoFocus
          required
          inputMode="numeric"
          autoComplete="off"
          pattern="[0-9]{6}"
          maxLength={6}
          placeholder="000000"
          value={code}
          disabled={action.busy}
          onChange={(event) =>
            setCode(event.target.value.replace(/\D/g, "").slice(0, 6))
          }
        />
        <button type="submit" disabled={action.busy || code.length !== 6}>
          {action.busy ? "Joining…" : "Go →"}
        </button>
      </form>
      <RequestError error={action.error} />
    </div>
  );
}

function ClassWorkspace({ classInfo, onChange }) {
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

  // Where the page opens: a ?view= / ?section= link wins, otherwise the
  // view and tabs you last had open in this class, otherwise the defaults.
  const memory = `class:${classInfo.id}`;
  const urlView = searchParams.get("view");
  const urlSection = searchParams.get("section");
  const urlTargetsUser = !showAdminLayout || urlView === "user";

  const [view, setView] = useRemembered(
    `${memory}:view`,
    showAdminLayout ? "admin" : "user",
    {
      override: !showAdminLayout
        ? "user"
        : urlView === "user" || urlView === "admin"
          ? urlView
          : urlSection
            ? "admin"
            : null,
      isValid: (value) =>
        value === "user" || (value === "admin" && showAdminLayout),
    },
  );

  // Also maps the old Quizzes, Students and Settings tab names.
  const adminStart = urlSection ? resolveAdminSection(urlSection) : null;
  const [adminSection, setAdminSection] = useRemembered(
    `${memory}:admin-section`,
    "Students",
    {
      override: urlTargetsUser ? null : adminStart?.section,
      isValid: (value) => ADMIN_SECTIONS.includes(value),
    },
  );
  const [userSection, setUserSection] = useRemembered(
    `${memory}:user-section`,
    "Present",
    {
      override:
        urlTargetsUser && urlSection ? resolveUserSection(urlSection) : null,
      isValid: (value) => USER_SECTIONS.includes(value),
    },
  );
  const [historyView, setHistoryView] = useRemembered(
    `${memory}:history-view`,
    "sessions",
    {
      override: !urlTargetsUser && urlSection === "Quizzes" ? "quizzes" : null,
      isValid: (value) => value in HISTORY_VIEWS,
    },
  );
  const [addOpen, setAddOpen] = useState(false);
  const [joinOpen, setJoinOpen] = useState(false);
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
  const activeSection = adminView ? adminSection : userSection;
  const setSection = adminView ? setAdminSection : setUserSection;

  // Keep the address in step with the open view and tab, so Back and
  // reload come back to the same place.
  useEffect(() => {
    const next = new URLSearchParams(searchParams);
    if (showAdminLayout) next.set("view", view);
    else next.delete("view");
    next.set("section", activeSection);
    if (next.toString() !== searchParams.toString()) {
      setSearchParams(next, { replace: true });
    }
  }, [view, activeSection, showAdminLayout, searchParams, setSearchParams]);
  const pendingApprovals =
    dashboard.status === "ready" ? dashboard.data.pending_submission_count : 0;

  function changeView(nextView) {
    setView(nextView);
    // Counts may be stale after time in the other view.
    dashboard.reload();
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
    <section
      className={`cl-page${adminView ? "" : " is-user-view"}`}
      aria-labelledby="class-heading"
    >
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
            // Same place, font and size as the heading, so nothing around
            // it moves. Enter saves, Escape cancels.
            <form className="cl-title-row cl-rename" onSubmit={saveName}>
              <label className="cl-rename-field">
                <span className="cl-sr">Class name</span>
                <textarea
                  rows={1}
                  value={nameDraft}
                  maxLength={100}
                  required
                  autoFocus
                  disabled={manage.busy}
                  onFocus={(event) => {
                    const end = event.target.value.length;
                    event.target.setSelectionRange(end, end);
                  }}
                  onChange={(event) =>
                    setNameDraft(event.target.value.replace(/\n/g, " "))
                  }
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      event.preventDefault();
                      event.currentTarget.form.requestSubmit();
                    }
                    if (event.key === "Escape") {
                      setNameDraft(classInfo.name);
                      setEditing(false);
                    }
                  }}
                />
              </label>
              <span className="cl-rename-actions">
                <button
                  type="submit"
                  className="cl-edit-name is-save"
                  disabled={manage.busy || !nameDraft.trim()}
                >
                  ✓ Save
                </button>
                <button
                  type="button"
                  className="cl-edit-name"
                  disabled={manage.busy}
                  onClick={() => {
                    setNameDraft(classInfo.name);
                    setEditing(false);
                  }}
                >
                  Cancel
                </button>
              </span>
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

        {adminView && (
          <div className="cl-actions">
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
          </div>
        )}

        {!adminView && classInfo.membershipStatus === "ACTIVE" && (
          <div className="cl-actions">
            <button
              type="button"
              className="cl-secondary cl-danger"
              disabled={leave.busy}
              onClick={() => void leaveClass()}
            >
              Leave class
            </button>
          </div>
        )}

        {/* Last in the bar, so it stays in the same spot in both views. */}
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
              data-section={label}
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

        {/* As in made-dashboard-main.html: a "+" cell for a new quiz and
            a JOIN cell that opens the session-code strip. */}
        {!adminView && (
          <div className="cl-actions">
            {classInfo.membershipStatus === "ACTIVE" && !classInfo.archived && (
              <Link
                className="cl-plus"
                to={`/app/quizzes/new?class=${classInfo.id}`}
                aria-label="New quiz"
                title="New quiz"
              >
                +
              </Link>
            )}

            <button
              type="button"
              className="cl-join"
              aria-expanded={joinOpen}
              aria-controls="cl-join-panel"
              onClick={() => setJoinOpen((open) => !open)}
            >
              Join
            </button>
          </div>
        )}
      </div>

      {/* Organizers keep their own quizzes and drafts in the User view;
          this keeps them one click away from the admin tabs. */}
      {adminView && classInfo.membershipStatus === "ACTIVE" && (
        <div className="cl-admin-quizzes">
          <span>Your own quizzes and drafts are in the User view.</span>
          <button
            type="button"
            className="cl-secondary"
            onClick={() => {
              setUserSection("Present");
              changeView("user");
            }}
          >
            My quizzes
          </button>
          {!classInfo.archived && (
            <Link
              className="cl-button"
              to={`/app/quizzes/new?class=${classInfo.id}`}
            >
              + New quiz
            </Link>
          )}
        </div>
      )}

      {!adminView && joinOpen && <JoinPanel />}

      {activeSection === "Students" ? (
        <ClassStudents
          classInfo={classInfo}
          dashboard={dashboard}
          onChange={onChange}
        />
      ) : activeSection === "Approvals" ? (
        <SubmissionsTable classInfo={classInfo} onChange={dashboard.reload} />
      ) : activeSection === "Present" ? (
        <PresentTable
          classInfo={classInfo}
          onApprovalChange={dashboard.reload}
        />
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
