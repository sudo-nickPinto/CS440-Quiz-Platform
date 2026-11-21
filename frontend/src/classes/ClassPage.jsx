import { useEffect, useState } from "react";
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
import { useAction, useApi, useResource } from "../authenticated-demo/rest";
import ClassLiveButton from "./ClassLiveButton";
import {
  ArchiveClassDialog,
  ArchivedBanner,
  SemesterDialog,
  TrashClassDialog,
} from "./ClassLifecycle";
import {
  ADMIN_SECTIONS,
  approvalLabel,
  approvalButton,
  collaboratorTags,
  copyText,
  formatScore,
  MY_QUIZ_SORTS,
  pluralNoun,
  presentStatus,
  resolveAdminSection,
  resolveUserSection,
  rowLink,
  sendForApproval,
  SUBMISSION_FILTERS,
  SUBMISSION_SORTS,
  USER_SECTIONS,
} from "./classHelpers";
import { ResourceMessage } from "./ClassUI";
import {
  DateBlock,
  Fraction,
  GoLink,
  ReportTable,
  ScoreMeter,
} from "./ReportTable";
import { ClassStudents } from "./ClassManagement";
import { AddStudentDialog, JoinRequestsTable } from "./StudentRoster";
import QuestionBankExportDialog from "../authenticated-demo/QuestionBankExportDialog";
import OptionsMenu from "../authenticated-demo/OptionsMenu";
import {
  CLASS_EVENTS,
  SUBMISSION_EVENTS,
  useClassDashboard,
  useClassQuizzes,
  useClassUpdates,
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

function reportResource(resource) {
  return resource.status === "ready" ? null : (
    <ResourceMessage resource={resource} />
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
  const nounLabel = pluralNoun(totalItems, noun);
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

const PRESENTATION_COLUMNS = ["", "", "cl-num", "", "cl-top-col", "cl-go-cell"];

const SESSION_DAY = new Intl.DateTimeFormat(undefined, {
  weekday: "short",
  month: "short",
  day: "numeric",
});
const SESSION_TIME = new Intl.DateTimeFormat(undefined, {
  hour: "numeric",
  minute: "2-digit",
});

function sessionWhen(value) {
  if (!value) return "—";
  const date = new Date(value);
  return `${SESSION_DAY.format(date)} · ${SESSION_TIME.format(date)}`;
}

// The presentations of one quiz, as rows under its opened Presentations row.
// Each opens that presentation's results.
function QuizSessionRows({ classId, quizId, studentCount }) {
  const navigate = useNavigate();
  const file = useFileDownload();
  const resource = useResource(`/classes/${classId}/quizzes/${quizId}/results`);

  if (resource.loading || resource.error || !resource.data) {
    return (
      <tr className="cl-sess-row cl-sess-foot">
        <td colSpan={PRESENTATION_COLUMNS.length}>
          {resource.error ? (
            <RequestError error={resource.error} retry={resource.reload} />
          ) : (
            <span role="status">Loading presentations…</span>
          )}
        </td>
      </tr>
    );
  }

  const sessions = resource.data.sessions;
  const rows = sessions.map((session, index) => {
    const to = `/app/classes/${classId}/sessions/${session.session_id}/report`;
    const when = sessionWhen(session.started_at);
    return (
      <tr
        key={session.session_id}
        {...rowLink(navigate, to)}
        className="cl-click-row cl-sess-row"
      >
        <td className="cl-sess-lead">
          <b>P{sessions.length - index}</b>
        </td>
        <td>
          <span className="cl-quiz-cell">
            <Link className="cl-quiz-name" to={to}>
              {when}
            </Link>
            <small>Hosted by {session.host_name}</small>
          </span>
        </td>
        <td className="cl-num">
          <Fraction value={session.participant_count} total={studentCount} />
        </td>
        <td>
          <ScoreMeter
            value={session.average_score}
            max={session.top_score}
            label={`Average ${formatScore(session.average_score)} points`}
          />
        </td>
        <td className="cl-top-col">
          <span className="cl-top-cell">
            <b>{formatScore(session.top_score)}</b>
            <small>top points</small>
          </span>
        </td>
        <td className="cl-go-cell">
          <GoLink to={to} label={`Results for ${when}`} />
        </td>
      </tr>
    );
  });

  // Every presentation of the quiz in one workbook (organizers only; the
  // tab itself is organizer-only).
  return (
    <>
      {rows}
      <tr className="cl-sess-row cl-sess-foot">
        <td colSpan={PRESENTATION_COLUMNS.length}>
          <span className="cl-sess-foot-in">
            {file.error && (
              <span className="cl-sess-foot-error" role="alert">
                {file.error.message}
              </span>
            )}
            <button
              type="button"
              className="cl-sess-export"
              disabled={file.busy}
              onClick={() =>
                void file.download(
                  `/classes/${classId}/quizzes/${quizId}/export.xlsx`,
                  `class-${classId}-quiz-${quizId}-results.xlsx`,
                )
              }
            >
              {file.busy
                ? "Preparing…"
                : `Export all ${sessions.length} to Excel`}
            </button>
          </span>
        </td>
      </tr>
    </>
  );
}

// Organizer view of the Presentations tab: one row per presented quiz,
// showing its most recent presentation. A quiz hosted once opens that
// session; one hosted more often opens in place to list its presentations,
// like a student's row on the Students tab.
function ClassHistory({ classInfo, studentCount }) {
  const memory = `class:${classInfo.id}:presentations`;
  const [page, setPage] = useRemembered(`${memory}:page`, 1);
  const [openId, setOpenId] = useRemembered(`${memory}:open`, null);
  const resource = useClassQuizzes(classInfo.id, page);
  const pending = reportResource(resource);
  if (pending) return pending;

  const { items, pagination } = resource.data;

  return (
    <ReportTable
      caption="Presentations"
      rememberAs={memory}
      noun="quiz"
      tableClass="cl-rows"
      columnClasses={PRESENTATION_COLUMNS}
      headers={["Last hosted", "Quiz", "Attended", "Avg score", "Top score", ""]}
      emptyTitle="No presentations yet"
      emptyText="Host a quiz in this class and it shows up here once it ends."
      pagination={pagination}
      onPageChange={setPage}
      rows={items.map((quiz) => {
        const once = quiz.session_count === 1;
        const open = !once && openId === quiz.quiz_id;
        const toggle = () => setOpenId(open ? null : quiz.quiz_id);
        const detailId = `cl-quiz-sessions-${quiz.quiz_id}`;
        const latest = `/app/classes/${classInfo.id}/sessions/${quiz.last_session_id}/report`;
        return {
          key: quiz.quiz_id,
          text: `${quiz.title} ${quiz.last_host_name}`,
          ...(once
            ? { to: latest }
            : {
                onToggle: toggle,
                open,
                after: open && (
                  <QuizSessionRows
                    key={detailId}
                    classId={classInfo.id}
                    quizId={quiz.quiz_id}
                    studentCount={studentCount}
                  />
                ),
              }),
          leadClass: "cl-date",
          cells: [
            <DateBlock value={quiz.presented_at} />,
            <span className="cl-quiz-cell">
              {once ? (
                <Link className="cl-quiz-name" to={latest}>
                  {quiz.title}
                </Link>
              ) : (
                <span className="cl-quiz-name">
                  {quiz.title}
                  <span className="cl-fold-count">
                    {quiz.session_count} presentations
                  </span>
                </span>
              )}
              <small>
                {once
                  ? `Hosted once by ${quiz.last_host_name}`
                  : `Latest shown · hosted by ${quiz.last_host_name}`}
              </small>
            </span>,
            <Fraction value={quiz.last_participant_count} total={studentCount} />,
            <ScoreMeter
              value={quiz.last_average_score}
              max={quiz.last_top_score}
              label={`Average ${formatScore(quiz.last_average_score)} points`}
            />,
            <span className="cl-top-cell">
              <b>{formatScore(quiz.last_top_score)}</b>
              <small>top points</small>
            </span>,
            once ? (
              <GoLink to={latest} label={`Results for ${quiz.title}`} />
            ) : (
              <button
                type="button"
                className="cl-stu-tog"
                aria-expanded={open}
                aria-controls={detailId}
                aria-label={`${open ? "Hide" : "Show"} every presentation of ${quiz.title}`}
                onClick={toggle}
              />
            ),
          ],
        };
      })}
    />
  );
}

// The member tabs can show quizzes as cards or as list rows; the choice is
// remembered across classes.
const LAYOUTS = { list: "Rows", cards: "Cards" };

function LayoutToggle({ layout, onChange }) {
  return (
    <div className="cl-toggle" role="group" aria-label="Layout">
      {Object.entries(LAYOUTS).map(([key, label]) => (
        <button
          key={key}
          type="button"
          aria-pressed={layout === key}
          onClick={() => onChange(key)}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

const PARTICIPATE_COLUMNS = ["", "", "cl-mid", "cl-wide", "cl-wide", "cl-go-cell"];

// Member view: completed and missed sessions, as cards or list rows.
function ParticipateTable({ classInfo, layout, onLayoutChange }) {
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
  const toggle = <LayoutToggle layout={layout} onChange={onLayoutChange} />;

  if (layout === "list") {
    return (
      <ReportTable
        caption="Sessions"
        rememberAs={memory}
        noun="session"
        tableClass="cl-rows cl-member-rows"
        columnClasses={PARTICIPATE_COLUMNS}
        headers={["Rank", "Quiz", "Score", "Host", "Date", ""]}
        emptyTitle="No sessions yet"
        emptyText={
          "When an organizer hosts a quiz here, a Live button appears at " +
          "the top of this page."
        }
        pagination={resource.data.pagination}
        onPageChange={setPage}
        controls={toggle}
        rows={resource.data.items.map((session) => {
          const played = session.my_score != null;
          const report =
            classInfo.canManage || played
              ? `/app/classes/${classInfo.id}/sessions/${session.session_id}/report`
              : null;
          return {
            key: session.session_id,
            text: `${session.quiz_title} ${session.host_name}`,
            to: report,
            leadClass: `cl-rank-lead${played ? "" : " is-none"}`,
            cells: [
              played ? (
                <span className="cl-rank-block">
                  <b>#{session.my_rank}</b>
                  <small>of {formatScore(session.participant_count)}</small>
                </span>
              ) : (
                "Absent"
              ),
              <span className="cl-quiz-cell">
                {report ? (
                  <Link className="cl-quiz-name" to={report}>
                    {session.quiz_title}
                  </Link>
                ) : (
                  <strong className="cl-quiz-name">{session.quiz_title}</strong>
                )}
                <small className="cl-meta">
                  {played && (
                    <span className="cl-phone-only">
                      {formatScore(session.my_score)} pts ·{" "}
                    </span>
                  )}
                  Hosted by {session.host_name} · {formatDate(session.started_at)}
                </small>
              </span>,
              played ? (
                <ScoreMeter
                  value={session.my_score}
                  max={session.top_score ?? best}
                  label={`Your score ${formatScore(session.my_score)} points`}
                />
              ) : (
                <span className="cl-dim">—</span>
              ),
              session.host_name,
              <span className="cl-dim">{formatDate(session.started_at)}</span>,
              report ? (
                <GoLink
                  to={report}
                  label={`${classInfo.canManage ? "Session report" : "My results"} for ${session.quiz_title}`}
                />
              ) : null,
            ],
          };
        })}
      />
    );
  }

  return (
    <CardCollection
      controls={toggle}
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
            wholeCard
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

const PRESENT_COLUMNS = ["", "", "cl-mid", "cl-wide", "cl-num cl-wide", "cl-wide", "cl-go-cell"];

// Member view: the caller's own quizzes in this class (owned or shared with
// them), as cards or list rows. Clicking a quiz opens the editor; Host live
// and the approval button stay on the card or row, and Archive lives in the
// editor.
function PresentTable({ classInfo, onApprovalChange, layout, onLayoutChange }) {
  const api = useApi();
  const account = useAccount();
  const action = useAction();
  const memory = `class:${classInfo.id}:present`;
  const [page, setPage] = useRemembered(`${memory}:page`, 1);
  const [sortKey, setSortKey] = useRemembered(`${memory}:sort`, "recent", {
    isValid: (key) => key in MY_QUIZ_SORTS,
  });
  const resource = useMyClassQuizzes(classInfo.id, page, sortKey);
  // An organizer approving or rejecting changes the status shown here.
  useClassUpdates(classInfo.id, SUBMISSION_EVENTS, resource.refresh);
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

  function describe(quiz) {
    const status = presentStatus(quiz);
    const archived = quiz.status === "ARCHIVED";
    const button = approvalButton(quiz);
    return {
      status,
      archived,
      owner: quiz.my_access === "OWNER",
      // Every quiz opens its page first; the Edit button there goes on to
      // the editor.
      to: `/app/quizzes/${quiz.quiz_id}`,
      hostable:
        status.key === "approved" &&
        !classInfo.archived &&
        showsHostControl(quiz, account?.account_id) &&
        hostingState(quiz, classInfo.id).canHost,
      button,
      // Send and Withdraw need an active membership in a live class.
      clickable: button && !button.disabled && canSubmit && !action.busy,
      press: () =>
        void (button.kind === "withdraw"
          ? withdraw(quiz)
          : submitForApproval(quiz)),
    };
  }

  // Ready to host: the one button starts the session. Otherwise it's the
  // approval button (send / withdraw). The status already says "Approved",
  // so the host button has no note under it and keeps the same height as
  // the ✓ Approved button on other cards and rows.
  function approvalControl(quiz, { hostable, button, clickable, press }, wrap) {
    if (hostable) {
      return (
        <div className={wrap}>
          <span className="qc-host">
            <HostQuizButton
              quiz={quiz}
              classId={classInfo.id}
              action={action}
              label="▶ Host live"
            />
          </span>
        </div>
      );
    }
    if (!button) return null;
    return (
      <div className={wrap}>
        <button
          type="button"
          className={`cl-send is-${button.kind}`}
          disabled={!clickable}
          aria-disabled={button.kind === "approved" || undefined}
          // The status ("Rejected", "Edited since approval") is a tooltip
          // now instead of a line under the button.
          title={button.title ?? button.note ?? undefined}
          onClick={press}
        >
          {button.label}
        </button>
      </div>
    );
  }

  const shared = {
    caption: "My quizzes",
    rememberAs: memory,
    noun: "quiz",
    emptyTitle: "No quizzes yet",
    emptyText: canSubmit
      ? "Start a draft for this class, or ask a classmate to share one with you. Drafts stay private until you send them for approval."
      : "Quizzes you own or that are shared with you in this class appear here.",
    emptyAction: canSubmit && (
      <Link className="cl-button" to={`/app/quizzes/new?class=${classInfo.id}`}>
        + New quiz
      </Link>
    ),
    pagination: resource.data.pagination,
    onPageChange: setPage,
    controls: (
      <>
        <SortSelect
          label="Sort my quizzes"
          value={sortKey}
          choices={MY_QUIZ_SORTS}
          onChange={(key) => {
            setSortKey(key);
            setPage(1);
          }}
        />
        <LayoutToggle layout={layout} onChange={onLayoutChange} />
      </>
    ),
  };

  if (layout === "list") {
    return (
      <>
        <RequestError error={action.error} />
        <ReportTable
          {...shared}
          tableClass="cl-rows cl-member-rows"
          columnClasses={PRESENT_COLUMNS}
          headers={["Status", "Quiz", "Approval", "People", "Qs", "Edited", ""]}
          rows={resource.data.items.map((quiz) => {
            const info = describe(quiz);
            return {
              key: quiz.quiz_id,
              text: `${quiz.title} ${quiz.author_name}`,
              leadClass: `cl-status is-${info.status.key}`,
              cells: [
                info.status.label,
                <span className="cl-quiz-cell">
                  <Link
                    className="cl-quiz-name"
                    to={info.to}
                    state={{ classId: classInfo.id }}
                  >
                    {quiz.title}
                  </Link>
                  <small className="cl-meta">
                    {quiz.question_count}{" "}
                    {quiz.question_count === 1 ? "question" : "questions"} ·
                    edited {formatDate(quiz.updated_at)}
                    {info.owner ? "" : ` · shared by ${quiz.author_name}`}
                  </small>
                </span>,
                approvalControl(quiz, info, "cl-approval-cell") ?? (
                  <span className="cl-dim">—</span>
                ),
                <PeopleTags quiz={quiz} owner={info.owner} />,
                <span className="cl-dim">{formatScore(quiz.question_count)}</span>,
                <span className="cl-dim">{formatDate(quiz.updated_at)}</span>,
                <GoLink to={info.to} label={`Open ${quiz.title}`} />,
              ],
            };
          })}
        />
      </>
    );
  }

  return (
    <>
      <RequestError error={action.error} />
      <CardCollection
        {...shared}
        items={resource.data.items}
        getText={(quiz) => `${quiz.title} ${quiz.author_name}`}
        renderCard={(quiz) => {
          const info = describe(quiz);
          const { status, owner, archived } = info;

          return (
            <QuizCard
              key={quiz.quiz_id}
              title={quiz.title}
              to={info.to}
              state={{ classId: classInfo.id }}
              wholeCard
              status={status.label}
              archived={archived}
              headline={`${quiz.question_count} ${
                quiz.question_count === 1 ? "question" : "questions"
              }`}
            >
              <PeopleTags quiz={quiz} owner={owner} long />
              <p>Edited {formatDate(quiz.updated_at)}</p>
              {approvalControl(quiz, info, "qc-approval")}
            </QuizCard>
          );
        }}
      />
    </>
  );
}

// The organizer's approval queue (Admin view): every submission in the class,
// pending first by default. Members follow their own requests in My quizzes.
const APPROVAL_COLUMNS = ["", "", "cl-wide", "cl-wide", "", "cl-go-cell"];

function SubmissionsTable({ classInfo, onChange, switcher = null }) {
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
  // New requests, withdrawals and other organizers' decisions.
  useClassUpdates(classInfo.id, SUBMISSION_EVENTS, resource.refresh);
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
        tableClass="cl-rows cl-approval-rows"
        columnClasses={APPROVAL_COLUMNS}
        headers={["Status", "Quiz", "Submitted by", "Submitted", "Decision", ""]}
        emptyTitle={
          status === "PENDING" ? "Nothing to review" : "No submissions"
        }
        emptyText="When a student sends a quiz for approval, it shows up here."
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
            {switcher}
          </>
        }
        rows={resource.data.items.map((item) => {
          const version = `v${item.version_number} · ${item.question_count} ${
            item.question_count === 1 ? "question" : "questions"
          }${item.is_current_version ? "" : " · outdated"}`;
          const preview = `/app/classes/${classInfo.id}/submissions/${item.submission_id}`;
          const pending = item.status === "PENDING";
          const actions = !pending ? (
            <span className="cl-approval-note">
              {item.decided_by_name
                ? `${approvalLabel(item.status)} by ${item.decided_by_name}`
                : "—"}
            </span>
          ) : (
              <span className="cl-approval">
                <button
                  type="button"
                  className="cl-decide is-approve"
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
                  className="cl-decide"
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
            leadClass: `cl-status is-${item.status.toLowerCase()}`,
            cells: [
              pending ? "Waiting" : approvalLabel(item.status),
              <span className="cl-quiz-cell">
                <Link
                  className="cl-quiz-name"
                  to={preview}
                  title="See exactly the version that was submitted"
                >
                  {item.quiz_title}
                </Link>
                <small>{version}</small>
              </span>,
              item.submitter_name,
              formatDate(item.submitted_at),
              actions,
              <GoLink to={preview} label={`Review ${item.quiz_title}`} />,
            ],
          };
        })}
      />
    </>
  );
}

// Approvals has two lists: quizzes sent for approval, and people who asked
// to join with the class code. The Quizzes / Students switch sits in each
// list's toolbar, just left of the counter, and shows its waiting counts.
const APPROVAL_TABS = ["Quizzes", "Students"];

function ApprovalsSection({ classInfo, dashboard }) {
  const [tab, setTab] = useRemembered(
    `class:${classInfo.id}:approvals-tab`,
    "Quizzes",
    { isValid: (value) => APPROVAL_TABS.includes(value) },
  );
  const ready = dashboard.status === "ready";
  const waiting = {
    Quizzes: ready ? dashboard.data.pending_submission_count : 0,
    Students: ready ? (dashboard.data.pending_join_request_count ?? 0) : 0,
  };

  const switcher = (
    <div
      className="cl-view-switch is-duo"
      role="group"
      aria-label="Approval lists"
    >
      {APPROVAL_TABS.map((label) => (
        <button
          key={label}
          type="button"
          aria-pressed={tab === label}
          onClick={() => setTab(label)}
        >
          {label}
          {waiting[label] > 0 && (
            <span className="cl-badge">
              {waiting[label]}
              <span className="cl-sr"> waiting</span>
            </span>
          )}
        </button>
      ))}
    </div>
  );

  return tab === "Students" ? (
    <JoinRequestsTable
      classInfo={classInfo}
      onChange={dashboard.reload}
      switcher={switcher}
    />
  ) : (
    <SubmissionsTable
      classInfo={classInfo}
      onChange={dashboard.reload}
      switcher={switcher}
    />
  );
}

function ClassWorkspace({ classInfo, onChange }) {
  const [searchParams, setSearchParams] = useSearchParams();
  const showAdminLayout = classInfo.canManage === true;
  const api = useApi();
  const confirmer = useConfirm();
  const [copied, setCopied] = useState(false);
  const csv = useFileDownload();
  const dashboard = useClassDashboard(classInfo.id);
  // The Approvals badge and the class's counts and live sessions.
  useClassUpdates(classInfo.id, CLASS_EVENTS, dashboard.refresh);
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
    "My quizzes",
    {
      override:
        urlTargetsUser && urlSection ? resolveUserSection(urlSection) : null,
      isValid: (value) => USER_SECTIONS.includes(value),
    },
  );
  // Rows or cards on the member tabs, shared by every class. Rows is the
  // default; the key changed when it did, so earlier choices start over.
  const [layout, setLayout] = useRemembered("class:member-layout-v2", "list", {
    isValid: (key) => key in LAYOUTS,
  });
  const [addOpen, setAddOpen] = useState(false);
  const [bankOpen, setBankOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const [nameDraft, setNameDraft] = useState(classInfo.name);
  // "archive", "trash" or "semester" while that dialog is open.
  const [lifecycleDialog, setLifecycleDialog] = useState(null);
  const manage = useAction();
  const navigate = useNavigate();

  function cancelRename() {
    setNameDraft(classInfo.name);
    setEditing(false);
  }

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

  async function lifecycleAction(path) {
    const done = await manage.run(async () => {
      await api(`/classes/${classInfo.id}/${path}`, { method: "POST" });
      return true;
    });
    if (done) setLifecycleDialog(null);
    return done;
  }

  async function archiveClass() {
    if (await lifecycleAction("archive")) onChange();
  }

  async function unarchiveClass() {
    const confirmed = await confirmer.confirm({
      label: "Unarchive class",
      title: `Unarchive ${classInfo.name}?`,
      message:
        "The class becomes active again with a new class code, and students " +
        "can ask to join. Quizzes and sessions can start again.",
      confirmLabel: "Unarchive class",
    });
    if (confirmed && (await lifecycleAction("unarchive"))) onChange();
  }

  async function trashClass() {
    if (await lifecycleAction("trash")) {
      navigate("/app/classes", { replace: true });
    }
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
  // Quizzes waiting for approval plus people waiting to join.
  const pendingApprovals =
    dashboard.status === "ready"
      ? dashboard.data.pending_submission_count +
        (dashboard.data.pending_join_request_count ?? 0)
      : 0;

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

  if (classInfo.archived && !showAdminLayout) {
    return (
      <section className="cl-page is-archived" aria-labelledby="class-heading">
        <p>
          <Link to="/app/classes">← Classes</Link>
        </p>
        <h1 id="class-heading">{classInfo.name}</h1>
        <p>
          This class is archived. Only its organizers can open quizzes,
          reports and grades.
        </p>
      </section>
    );
  }


  return (
    <section
      className={`cl-page${adminView ? "" : " is-user-view"}${
        classInfo.archived ? " is-archived" : ""
      }`}
      aria-labelledby="class-heading"
    >
      <ConfirmDialog confirmer={confirmer} />

      {lifecycleDialog === "archive" && (
        <ArchiveClassDialog
          classInfo={classInfo}
          busy={manage.busy}
          error={manage.error}
          onCancel={() => setLifecycleDialog(null)}
          onConfirm={() => void archiveClass()}
        />
      )}

      {lifecycleDialog === "trash" && (
        <TrashClassDialog
          classInfo={classInfo}
          busy={manage.busy}
          error={manage.error}
          onCancel={() => setLifecycleDialog(null)}
          onConfirm={() => void trashClass()}
        />
      )}

      {lifecycleDialog === "semester" && (
        <SemesterDialog
          classInfo={classInfo}
          onClose={() => setLifecycleDialog(null)}
          onChanged={onChange}
        />
      )}

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

            {classInfo.semester && (
              <span className="cl-chip cl-chip-semester">
                {classInfo.semester}
              </span>
            )}

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
                    if (event.key === "Escape") cancelRename();
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
                  onClick={cancelRename}
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
                  aria-label={`Edit class name for ${classInfo.name}`}
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
              + Add student
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

            {/* Less frequent actions, like the quiz page's ⋯ menu. Archive
                is a simple confirm; Move to trash asks for the class name. */}
            <OptionsMenu className="cl-class-options">
              <button
                type="button"
                aria-haspopup="dialog"
                onClick={() => setBankOpen(true)}
              >
                Question bank
              </button>
              <button
                type="button"
                aria-haspopup="dialog"
                onClick={() => setLifecycleDialog("semester")}
              >
                Semester
              </button>
              {classInfo.archived ? (
                <button
                  type="button"
                  disabled={manage.busy}
                  onClick={() => void unarchiveClass()}
                >
                  Unarchive class
                </button>
              ) : (
                <button
                  type="button"
                  aria-haspopup="dialog"
                  className="ui-danger"
                  disabled={manage.busy}
                  onClick={() => setLifecycleDialog("archive")}
                >
                  Archive class
                </button>
              )}
              <button
                type="button"
                aria-haspopup="dialog"
                className="ui-danger"
                disabled={manage.busy}
                onClick={() => setLifecycleDialog("trash")}
              >
                Move to trash
              </button>
            </OptionsMenu>
          </div>
        )}

        {/* Last in the bar, so it stays in the same spot in both views. */}
        {showAdminLayout && (
          <div
            className="cl-view-switch is-duo"
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

      {adminView && bankOpen && (
        <QuestionBankExportDialog
          classId={classInfo.id}
          className={classInfo.name}
          onClose={() => setBankOpen(false)}
        />
      )}

      {adminView && addOpen && (
        <AddStudentDialog
          classInfo={classInfo}
          onClose={() => setAddOpen(false)}
          onChange={dashboard.reload}
        />
      )}

      <ClassLiveButton classId={classInfo.id} />

      {classInfo.archived && (
        <ArchivedBanner
          classInfo={classInfo}
          busy={manage.busy}
          onUnarchive={() => void unarchiveClass()}
        />
      )}

      <RequestError
        error={lifecycleDialog ? csv.error : csv.error || manage.error}
      />

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

        {/* As in made-dashboard-main.html: a "+" cell for a new quiz.
            Students join live quizzes from the class live button above. */}
        {!adminView && (
          <div className="cl-actions">
            {classInfo.membershipStatus === "ACTIVE" && !classInfo.archived && (
              <Link
                className="cl-plus"
                to={`/app/quizzes/new?class=${classInfo.id}`}
              >
                <span aria-hidden="true">+</span> New quiz
              </Link>
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
        <ApprovalsSection classInfo={classInfo} dashboard={dashboard} />
      ) : activeSection === "My quizzes" ? (
        <PresentTable
          classInfo={classInfo}
          onApprovalChange={dashboard.reload}
          layout={layout}
          onLayoutChange={setLayout}
        />
      ) : activeSection === "Presentations" ? (
        <ClassHistory
          classInfo={classInfo}
          studentCount={studentCount}
        />
      ) : (
        <ParticipateTable
          classInfo={classInfo}
          layout={layout}
          onLayoutChange={setLayout}
        />
      )}
    </section>
  );
}

// Who has the quiz: the owner tag ("Me" or "Shared · owner"), then one tag
// per other editor, up to three, and "+N" for the rest. `long` uses the
// card wording ("Owned by me", "Shared by ...").
function PeopleTags({ quiz, owner, long = false }) {
  const { shown, rest } = collaboratorTags(quiz.collaborator_names);
  const all = quiz.collaborator_names ?? [];
  return (
    <span className="cl-people-tags">
      {owner ? (
        <span className="cl-tag is-owner">{long ? "Owned by me" : "Me"}</span>
      ) : (
        <span className="cl-tag is-owner" title="Owner">
          {long ? `Shared by ${quiz.author_name}` : `Shared · ${quiz.author_name}`}
        </span>
      )}
      {shown.map((name) => (
        <span className="cl-tag is-editor" key={name} title="Editor">
          {name}
        </span>
      ))}
      {rest > 0 && (
        <span className="cl-tag is-editor" title={all.slice(3).join(", ")}>
          +{rest}
        </span>
      )}
    </span>
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
