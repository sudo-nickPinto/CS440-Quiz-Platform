import { Fragment, useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import { useAccount } from "../authenticated-demo/account";

import { useAction, useApi, useResource } from "../authenticated-demo/rest";
import ConfirmDialog from "../authenticated-demo/ConfirmDialog";
import { useConfirm } from "../authenticated-demo/useConfirm";
import { ResourceMessage } from "./ClassUI";
import {
  initials,
  MEMBER_SORTS,
  membersWithStats,
  scoreMark,
  studentRanks,
} from "./classHelpers";
import { useClassSessions, useClassStudentStats } from "./classResources";

// Whole points: averages like 2,192.2 read as 2,192.
function formatPoints(value) {
  return value === null || value === undefined
    ? "—"
    : Math.round(Number(value)).toLocaleString();
}

function formatRate(value) {
  return value === null || value === undefined
    ? "—"
    : `${Math.round(value * 100)}%`;
}

const SHORT_DATE = new Intl.DateTimeFormat(undefined, {
  month: "short",
  day: "numeric",
});

function shortDate(value) {
  return value ? SHORT_DATE.format(new Date(value)) : "—";
}

function personName(person) {
  return person.display_name || person.email;
}

// The Students tab: every student once with rank, recent scores, average
// and attendance, then any co-organizers. A row opens to show each
// presentation the student was part of, plus the role and remove actions.
export function ClassStudents({ classInfo, dashboard, onChange }) {
  const account = useAccount();
  const api = useApi();
  const action = useAction();
  const confirmer = useConfirm();

  const resource = useResource(`/classes/${classInfo.id}/members`);
  const stats = useClassStudentStats(classInfo.id);
  // The newest page of presentations labels the recent-score chips; the
  // students report lists recent scores newest first, in the same order.
  const sessions = useClassSessions(classInfo.id, 1);

  const [query, setQuery] = useState("");
  const [sortKey, setSortKey] = useState("average");
  const [openId, setOpenId] = useState(null);

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

  async function changeRole(member) {
    const nextRole = member.role === "ORGANIZER" ? "MEMBER" : "ORGANIZER";
    const confirmed = await confirmer.confirm({
      label: "Change role",
      title: `Make ${personName(member)} ${
        nextRole === "ORGANIZER" ? "an organizer" : "a student"
      }?`,
      message:
        nextRole === "ORGANIZER"
          ? "Organizers can add, remove and manage members."
          : "They will no longer be able to manage this class.",
      confirmLabel: nextRole === "ORGANIZER" ? "Make organizer" : "Make student",
    });
    if (!confirmed) return;

    const succeeded = await action.run(async () => {
      await api(`/classes/${classInfo.id}/members/${member.account_id}`, {
        method: "PATCH",
        body: JSON.stringify({ role: nextRole }),
      });
      return true;
    });
    if (succeeded) refreshAfterMemberChange(member);
  }

  async function removeMember(member) {
    const confirmed = await confirmer.confirm({
      label: "Remove member",
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
            resource.error ?? new Error("The member list could not be read."),
          reload: resource.reload,
        }}
      />
    );
  }

  const rows = membersWithStats(resource.data, stats.data, sortKey);
  const ranks = studentRanks(rows);
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
            <dd>{summary ? formatRate(summary.attendance_rate) : "—"}</dd>
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
              <th scope="col" className="cl-num cl-stu-att">Attended</th>
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
              const recent = member.stats?.recent_scores ?? [];
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
                      <strong className="cl-stu-name">{personName(member)}</strong>
                      {member.display_name &&
                        member.display_name !== member.email && (
                          <small>{member.email}</small>
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
                          aria-label={`Recent scores, oldest to newest: ${[...recent]
                            .reverse()
                            .map((score) => (score === null ? "absent" : score))
                            .join(", ")}`}
                        >
                          {[...recent].reverse().map((score, index) => {
                            const session =
                              recentSessions[recent.length - 1 - index];
                            return (
                              <i
                                key={index}
                                className={`cl-mk ${scoreMark(
                                  score,
                                  session?.average_score,
                                )}`}
                                title={session?.quiz_title}
                              >
                                {score === null ? "–" : formatPoints(score)}
                              </i>
                            );
                          })}
                        </span>
                      )}
                    </td>
                    <td className="cl-num cl-big">
                      {organizer ? "" : formatPoints(member.stats?.average_score)}
                    </td>
                    <td className="cl-num cl-big cl-stu-att">
                      {organizer || !member.stats ? (
                        ""
                      ) : (
                        <span className="cl-fraction">
                          <b>{member.stats.session_count}</b>
                          <small> / {completed}</small>
                        </span>
                      )}
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
                          completed={completed}
                          busy={action.busy}
                          onChangeRole={() => void changeRole(member)}
                          onRemove={() => void removeMember(member)}
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
                        : "Share the class code or use + Add member."}
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
        class average and orange below it. The last active organizer cannot be
        removed or made a student.
      </p>
    </section>
  );
}

// One opened Students row: the student's presentations (from their class
// report), and the actions for this person.
function StudentDetail({
  classInfo,
  member,
  completed,
  busy,
  onChangeRole,
  onRemove,
}) {
  const organizer = member.role === "ORGANIZER";
  const report = useResource(
    organizer
      ? null
      : `/classes/${classInfo.id}/students/${member.account_id}/results`,
  );
  const reportPath = `/app/classes/${classInfo.id}/students/${member.account_id}/report`;

  return (
    <div className="cl-panel">
      <div className="cl-panel-top">
        <span>
          {personName(member)} ·{" "}
          {organizer ? "organizer" : "every presentation"}
        </span>
        {!organizer && member.stats && (
          <span>
            Avg {formatPoints(member.stats.average_score)} ·{" "}
            {member.stats.session_count}/{completed} attended
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
                <th scope="col">
                  <span className="cl-sr">Played</span>
                </th>
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
              {report.data.sessions.map((session) => (
                <tr
                  key={session.session_id}
                  className={session.played ? "" : "is-missed"}
                >
                  <td className={`cl-mk ${session.played ? "hi" : "miss"}`}>
                    {session.played ? "✓" : "–"}
                  </td>
                  <td className="cl-gl-date">{shortDate(session.started_at)}</td>
                  <td className="cl-gl-quiz">{session.quiz_title}</td>
                  <td className="cl-num">
                    {session.played
                      ? `${session.correct}/${session.correct + session.incorrect}`
                      : "Absent"}
                  </td>
                  <td className="cl-num cl-big">
                    {session.played ? formatPoints(session.points) : "—"}
                  </td>
                  <td className="cl-num">
                    {session.rank ? `#${session.rank}` : "—"}
                  </td>
                  <td className="cl-gl-go">
                    {session.played && (
                      <Link
                        className="cl-lnk"
                        to={`/app/classes/${classInfo.id}/sessions/${session.session_id}/report`}
                      >
                        Results →
                      </Link>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ))}

      <div className="cl-panel-foot">
        {!organizer && (
          <Link className="cl-button cl-secondary" to={reportPath}>
            Full report →
          </Link>
        )}
        <button
          type="button"
          className="cl-secondary"
          disabled={busy || classInfo.archived}
          onClick={onChangeRole}
        >
          {organizer ? "Make student" : "Make organizer"}
        </button>
        <button
          type="button"
          className="cl-secondary cl-danger"
          disabled={busy || classInfo.archived}
          onClick={onRemove}
        >
          Remove from class
        </button>
      </div>
    </div>
  );
}

// "+ Add member" pop-up: invite by account email, and see or cancel the
// invitations still waiting to be accepted.
export function AddMemberDialog({ classInfo, onClose }) {
  const ref = useRef(null);
  const api = useApi();
  const action = useAction();
  const invites = useResource(`/classes/${classInfo.id}/invites`);
  const [email, setEmail] = useState("");
  const [added, setAdded] = useState(0);

  useEffect(() => {
    const dialog = ref.current;
    if (dialog && !dialog.open) dialog.showModal();
  }, []);

  async function invite(event) {
    event.preventDefault();
    const sent = await action.run(() =>
      api(`/classes/${classInfo.id}/invites`, {
        method: "POST",
        body: JSON.stringify({ email: email.trim() }),
      }),
    );
    if (sent) {
      setEmail("");
      setAdded((count) => count + 1);
      invites.reload();
    }
  }

  async function cancel(invitation) {
    const done = await action.run(async () => {
      await api(`/classes/${classInfo.id}/invites/${invitation.account_id}`, {
        method: "DELETE",
      });
      return true;
    });
    if (done) invites.reload();
  }

  const pending = Array.isArray(invites.data) ? invites.data : [];

  return (
    <dialog
      ref={ref}
      className="cl-dlg"
      aria-labelledby="cl-add-title"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClick={(event) => {
        // A click on the backdrop lands on the <dialog> itself.
        if (event.target === ref.current) onClose();
      }}
    >
      <div className="cl-dlg-top">
        <span>
          Add member{classInfo.code && <> · <b>{classInfo.code}</b></>}
        </span>
        <button
          type="button"
          className="cl-dlg-x"
          aria-label="Close"
          onClick={onClose}
        >
          ×
        </button>
      </div>

      <form className="cl-dlg-head" onSubmit={invite}>
        <h2 id="cl-add-title">Add someone to this class</h2>
        <div className="cl-dlg-row">
          <label className="cl-search">
            <span className="cl-sr">Account email</span>
            <input
              type="email"
              placeholder="Their QuizBurg account email…"
              value={email}
              autoFocus
              required
              disabled={action.busy || classInfo.archived}
              onChange={(event) => setEmail(event.target.value)}
            />
          </label>
          <button
            type="submit"
            className="cl-add-one"
            disabled={action.busy || classInfo.archived || !email.trim()}
          >
            + Invite
          </button>
        </div>
        <p>
          {classInfo.archived
            ? "This class is archived, so no one new can join."
            : "They need a QuizBurg account and accept the invite from their Classes page" +
              (classInfo.code && classInfo.joiningOpen
                ? `, or they can join with code ${classInfo.code}.`
                : ".")}
        </p>
        {action.error && (
          <p className="cl-dlg-error" role="alert">
            {action.error.message}
          </p>
        )}
      </form>

      <div className="cl-dlg-sub">
        <span>Waiting to accept</span>
        <span>
          {pending.length} {pending.length === 1 ? "person" : "people"}
        </span>
      </div>

      <div className="cl-people">
        {invites.loading ? (
          <p className="cl-dlg-empty" role="status">
            Loading invitations…
          </p>
        ) : invites.error ? (
          <p className="cl-dlg-empty" role="alert">
            {invites.error.message}{" "}
            <button type="button" onClick={invites.reload}>
              Retry
            </button>
          </p>
        ) : pending.length === 0 ? (
          <p className="cl-dlg-empty">No pending invitations.</p>
        ) : (
          pending.map((invitation) => (
            <div className="cl-person" key={invitation.account_id}>
              <span className="cl-pav" aria-hidden="true">
                {initials(personName(invitation))}
              </span>
              <span>
                <strong className="cl-pname">{personName(invitation)}</strong>
                {invitation.display_name &&
                  invitation.display_name !== invitation.email && (
                    <small className="cl-pmail">{invitation.email}</small>
                  )}
              </span>
              <button
                type="button"
                className="cl-secondary"
                disabled={action.busy}
                onClick={() => void cancel(invitation)}
              >
                Cancel
              </button>
            </div>
          ))
        )}
      </div>

      <div className="cl-dlg-foot">
        <span aria-live="polite">
          {added === 0 ? (
            "Nobody invited yet"
          ) : (
            <>
              <b>{added}</b> invited
            </>
          )}
        </span>
        <button type="button" className="cl-add-one" onClick={onClose}>
          Done
        </button>
      </div>
    </dialog>
  );
}
