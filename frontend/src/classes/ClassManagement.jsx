import { Fragment } from "react";
import { useRemembered } from "../authenticated-demo/remember";
import { Link, useNavigate } from "react-router";
import { useAccount } from "../authenticated-demo/account";

import { useAction, useApi, useResource } from "../authenticated-demo/rest";
import ConfirmDialog from "../authenticated-demo/ConfirmDialog";
import { useConfirm } from "../authenticated-demo/useConfirm";
import { ResourceMessage } from "./ClassUI";
import {
  attendanceLabel,
  formatAttendanceRate,
  MEMBER_SORTS,
  membersWithStats,
  rowLink,
  scoreMark,
  sessionResultsPath,
  studentRanks,
} from "./classHelpers";
import { useClassSessions, useClassStudentStats } from "./classResources";

// Whole points: averages like 2,192.2 read as 2,192.
function formatPoints(value) {
  return value === null || value === undefined
    ? "—"
    : Math.round(Number(value)).toLocaleString();
}

const SHORT_DATE = new Intl.DateTimeFormat(undefined, {
  month: "short",
  day: "numeric",
});

function shortDate(value) {
  return value ? SHORT_DATE.format(new Date(value)) : "—";
}

// An email that, on a narrow screen, wraps after the "@" or before a dot
// instead of in the middle of a word.
function EmailText({ email }) {
  const parts = email.split(/(?<=@)|(?=[.])/);
  return parts.map((part, index) => (
    <Fragment key={index}>
      {index > 0 && <wbr />}
      {part}
    </Fragment>
  ));
}

function personName(person) {
  return person.display_name || person.email;
}

// The Students tab: every student once with rank, recent scores, average
// and attendance, then any co-organizers. A row opens to show each
// presentation the student was part of. Removing a student is on their full
// report; a co-organizer's row keeps its own Remove button (they have no
// report).
export function ClassStudents({ classInfo, dashboard, onChange }) {
  const account = useAccount();
  const api = useApi();
  const action = useAction();
  const confirmer = useConfirm();

  const resource = useResource(`/classes/${classInfo.id}/members`);
  const stats = useClassStudentStats(classInfo.id);
  // Recent attendance and scores use the same newest-first order as these
  // sessions. Match them by index before reversing for display.
  const sessions = useClassSessions(classInfo.id, 1);

  const memory = `class:${classInfo.id}:students`;
  const [query, setQuery] = useRemembered(`${memory}:query`, "");
  const [sortKey, setSortKey] = useRemembered(`${memory}:sort`, "average", {
    isValid: (key) => key in MEMBER_SORTS,
  });
  const [openId, setOpenId] = useRemembered(`${memory}:open`, null);

  const summary = dashboard.status === "ready" ? dashboard.data : null;
  const completed = summary?.completed_session_count ?? 0;
  const recentSessions =
    sessions.status === "ready" ? sessions.data.items.slice(0, 5) : [];

  function refreshAfterMemberChange(member) {
    if (Number(member.account_id) === Number(account.account_id)) {
      // Recheck access when the signed-in user's own membership changes.
      onChange();
    } else {
      resource.reload();
      stats.reload();
      dashboard.reload?.();
    }
  }

  async function removeOrganizer(member) {
    const confirmed = await confirmer.confirm({
      label: "Remove organizer",
      title: `Remove ${personName(member)}?`,
      message: "They will lose access to this class.",
      confirmLabel: "Remove",
    });
    if (!confirmed) return;

    const succeeded = await action.run(async () => {
      await api(`/classes/${classInfo.id}/members/${member.account_id}`, {
        method: "DELETE",
      });
      return true;
    });
    if (succeeded) {
      setOpenId(null);
      refreshAfterMemberChange(member);
    }
  }

  if (resource.loading) {
    return <ResourceMessage resource={{ status: "loading" }} />;
  }

  if (resource.error || !Array.isArray(resource.data)) {
    return (
      <ResourceMessage
        resource={{
          status:
            resource.error?.status === 403
              ? "forbidden"
              : resource.error?.status === 404
                ? "not-found"
                : "error",
          error:
            resource.error ?? new Error("The student list could not be read."),
          reload: resource.reload,
        }}
      />
    );
  }

  const rows = membersWithStats(resource.data, stats.data, sortKey);
  const ranks = studentRanks(rows);
  // Searches this class's list, like the search bar on every other tab.
  // "+ Add student" is the search across every QuizBurg account.
  const needle = query.trim().toLowerCase();
  const visible = rows.filter((member) =>
    `${member.display_name ?? ""} ${member.email}`.toLowerCase().includes(needle),
  );
  const studentTotal = rows.filter((row) => row.role !== "ORGANIZER").length;

  return (
    <section aria-label="Students" className="cl-students">
      <ConfirmDialog confirmer={confirmer} />

      <div className="cl-toolbar">
        <label className="cl-search">
          <span className="cl-sr">Search students</span>
          <input
            type="search"
            placeholder="Search students…"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>

        <label className="cl-sort">
          <span className="cl-sr">Sort students</span>
          <select
            value={sortKey}
            onChange={(event) => setSortKey(event.target.value)}
          >
            {Object.entries(MEMBER_SORTS).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </label>

        <dl className="cl-mini-stats" aria-label="Class summary">
          <div>
            <dt>Presentations</dt>
            <dd>{summary ? formatPoints(completed) : "—"}</dd>
          </div>
          <div>
            <dt>Class avg</dt>
            <dd>{summary ? formatPoints(summary.class_average) : "—"}</dd>
          </div>
          <div>
            <dt>Attendance</dt>
            <dd>{summary ? formatAttendanceRate(summary.attendance_rate) : "—"}</dd>
          </div>
        </dl>

        <span className="cl-count" aria-live="polite">
          {studentTotal} {studentTotal === 1 ? "student" : "students"}
        </span>
      </div>

      {action.error && (
        <p className="cl-feedback cl-error" role="alert">
          {action.error.message}
        </p>
      )}

      {stats.error && (
        <p className="cl-feedback cl-error" role="alert">
          Scores could not be loaded: {stats.error.message}{" "}
          <button type="button" onClick={stats.reload}>
            Retry scores
          </button>
        </p>
      )}

      <div className="cl-table-wrap">
        <table className="cl-table cl-stu-table">
          <caption className="cl-sr">Students and organizers</caption>

          <thead>
            <tr>
              <th scope="col">Rank</th>
              <th scope="col">Student</th>
              <th scope="col" className="cl-stu-recent">
                Recent
              </th>
              <th scope="col" className="cl-num">Avg</th>
              <th scope="col" className="cl-num cl-stu-att">Attendance</th>
              <th scope="col">
                <span className="cl-sr">Details</span>
              </th>
            </tr>
          </thead>

          <tbody>
            {visible.map((member) => {
              const id = Number(member.account_id);
              const organizer = member.role === "ORGANIZER";
              const open = openId === id;
              const rank = ranks.get(id);
              const scores = member.stats?.recent_scores ?? [];
              const statuses = member.stats?.recent_attendance_statuses ?? [];
              const recent = scores.map((score, index) => ({
                score,
                status: attendanceLabel(statuses[index], score != null),
                session: recentSessions[index],
              })).reverse();
              const detailId = `cl-stu-detail-${id}`;

              return (
                <Fragment key={id}>
                  <tr
                    className="cl-stu-row"
                    data-open={open}
                    onClick={() => setOpenId(open ? null : id)}
                  >
                    <td
                      className={`cl-stu-lead${
                        organizer ? " is-org" : rank ? "" : " is-none"
                      }`}
                    >
                      {organizer ? "Org" : (rank ?? "—")}
                    </td>
                    <td className="cl-stu-who">
                      {/* A student's name opens their full report, like
                          "Full report" in the opened row; the rest of the
                          row still opens the row. */}
                      {organizer ? (
                        <strong className="cl-stu-name">{personName(member)}</strong>
                      ) : (
                        <Link
                          className="cl-stu-name"
                          to={`/app/classes/${classInfo.id}/students/${id}/report`}
                          onClick={(event) => event.stopPropagation()}
                        >
                          {personName(member)}
                        </Link>
                      )}
                      {member.display_name &&
                        member.display_name !== member.email && (
                          <small>
                            <EmailText email={member.email} />
                          </small>
                        )}
                    </td>
                    <td className="cl-stu-recent">
                      {organizer ? (
                        <small>Organizer</small>
                      ) : stats.loading ? (
                        "…"
                      ) : (
                        <span
                          className="cl-stu-strip"
                          role="group"
                          aria-label="Recent attendance, oldest to newest"
                        >
                          {recent.map(({ score, status, session }, index) => (
                            <span
                              key={index}
                              className={`cl-mk ${status === "Played" ? scoreMark(score, session?.average_score) : "miss"}`}
                              title={session?.quiz_title}
                            >
                              {status === "Played" ? `Played · ${formatPoints(score)}` : status}
                            </span>
                          ))}
                        </span>
                      )}
                    </td>
                    <td className="cl-num cl-big">
                      {organizer ? "" : formatPoints(member.stats?.average_score)}
                    </td>
                    <td className="cl-num cl-big cl-stu-att">
                      {!organizer && member.stats && formatAttendanceRate(member.stats.attendance_rate)}
                    </td>
                    <td className="cl-stu-tog-cell">
                      <button
                        type="button"
                        className="cl-stu-tog"
                        aria-expanded={open}
                        aria-controls={detailId}
                        aria-label={`${open ? "Hide" : "Show"} ${personName(member)}'s details`}
                        onClick={(event) => {
                          event.stopPropagation();
                          setOpenId(open ? null : id);
                        }}
                      />
                    </td>
                  </tr>

                  {open && (
                    <tr className="cl-stu-xp" id={detailId}>
                      <td colSpan={6}>
                        <StudentDetail
                          classInfo={classInfo}
                          member={member}
                          busy={action.busy}
                          onRemove={() => void removeOrganizer(member)}
                        />
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}

            {visible.length === 0 && (
              <tr>
                <td colSpan={6}>
                  <div className="cl-state" role="status">
                    <h2>{needle ? "No matches" : "No students yet"}</h2>
                    <p>
                      {needle
                        ? "Try another search."
                        : "Share the class code or use + Add student."}
                    </p>
                  </div>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <p className="cl-section-note">
        Scores are points. A chip is blue at or above that presentation&apos;s
        class average and orange below it. To remove a student, open their
        full report. The last active organizer cannot be removed.
      </p>
    </section>
  );
}

// One opened Students row: the student's presentations (from their class
// report), and the actions for this person.
function StudentDetail({
  classInfo,
  member,
  busy,
  onRemove,
}) {
  const organizer = member.role === "ORGANIZER";
  const report = useResource(
    organizer
      ? null
      : `/classes/${classInfo.id}/students/${member.account_id}/results`,
  );
  const navigate = useNavigate();
  const reportPath = `/app/classes/${classInfo.id}/students/${member.account_id}/report`;

  return (
    <div className="cl-panel">
      <div className="cl-panel-top">
        <span>
          {personName(member)} ·{" "}
          {organizer ? "organizer" : "every presentation"}
        </span>
        {report.data && (
          <span>
            Avg {formatPoints(report.data.average_score)} ·{" "}
            {report.data.attendance_rate == null ? "No eligible sessions" : (
              <>
                {formatAttendanceRate(report.data.attendance_rate)} attendance ·{" "}
                {report.data.attendance_session_count} eligible{" "}
                {report.data.attendance_session_count === 1 ? "session" : "sessions"}
              </>
            )}
          </span>
        )}
      </div>

      {!organizer &&
        (report.loading ? (
          <p className="cl-panel-note" role="status">
            Loading presentations…
          </p>
        ) : report.error ? (
          <p className="cl-panel-note" role="alert">
            {report.error.message}{" "}
            <button type="button" onClick={report.reload}>
              Retry
            </button>
          </p>
        ) : !report.data?.sessions?.length ? (
          <p className="cl-panel-note">No completed presentations yet.</p>
        ) : (
          <table className="cl-gl">
            <caption className="cl-sr">
              {personName(member)}&apos;s presentations
            </caption>
            <thead>
              <tr>
                <th scope="col">Attendance</th>
                <th scope="col">Date</th>
                <th scope="col">Presentation</th>
                <th scope="col" className="cl-num">Correct</th>
                <th scope="col" className="cl-num">Points</th>
                <th scope="col" className="cl-num">Rank</th>
                <th scope="col">
                  <span className="cl-sr">Results</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {report.data.sessions.map((session) => {
                const status = attendanceLabel(session.attendance_status, session.played);
                const played = status === "Played";
                const to = sessionResultsPath(classInfo.id, session.session_id, {
                  canViewClassReport: classInfo.canManage,
                });
                return (
                  <tr key={session.session_id} {...(to && rowLink(navigate, to))}>
                    <td className={`cl-mk ${played ? "hi" : "miss"}`}>{status}</td>
                    <td className="cl-gl-date">{shortDate(session.started_at)}</td>
                    <td className="cl-gl-quiz">{session.quiz_title}</td>
                    <td className="cl-num">
                      {played ? `${session.correct}/${session.correct + session.incorrect}` : "—"}
                    </td>
                    <td className="cl-num cl-big">
                      {played ? formatPoints(session.points) : "—"}
                    </td>
                    <td className="cl-num">{played && session.rank ? `#${session.rank}` : "—"}</td>
                    <td className="cl-gl-go">
                      {to && <Link className="cl-lnk" to={to}>Results →</Link>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        ))}

      <div className="cl-panel-foot">
        {organizer ? (
          <button
            type="button"
            className="cl-secondary cl-danger"
            disabled={busy || classInfo.archived}
            onClick={onRemove}
          >
            Remove from class
          </button>
        ) : (
          <Link className="cl-button cl-secondary" to={reportPath}>
            Full report →
          </Link>
        )}
      </div>
    </div>
  );
}
