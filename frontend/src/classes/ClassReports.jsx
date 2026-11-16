import { Link, useNavigate, useParams } from "react-router";
import { useResource } from "../authenticated-demo/rest";
import RequestError from "../authenticated-demo/RequestError";
import {
  HostResults,
  ParticipantResults,
} from "../authenticated-demo/SessionResults";
import { useFileDownload } from "../authenticated-demo/useFileDownload";
import { formatScore, rowLink } from "./classHelpers";
import {
  DateBlock,
  Fraction,
  GoLink,
  ReportTable,
  ScoreMeter,
} from "./ReportTable";

function validId(value) {
  return (
    /^[1-9]\d*$/.test(String(value ?? "")) &&
    Number.isSafeInteger(Number(value))
  );
}

function number(value) {
  return value == null ? "—" : Number(value).toLocaleString();
}

function date(value) {
  if (!value) return "—";

  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? "—" : parsed.toLocaleString();
}

function sessionUrl(classId, sessionId) {
  return `/app/classes/${classId}/sessions/${sessionId}/report`;
}

function ReportFrame({ classId, title, actions, error, children }) {
  return (
    <section className="cl-page">
      <header className="cl-classbar">
        <Link
          className="cl-button cl-secondary"
          to={validId(classId) ? `/app/classes/${classId}` : "/app/classes"}
        >
          ← Class dashboard
        </Link>

        <div className="cl-class-title">
          <p className="cl-eyebrow">Class report</p>
          <h1>{title}</h1>
        </div>

        {actions}
      </header>

      <RequestError error={error} />

      {children}
    </section>
  );
}

function ReportRequest({ valid, resource, children }) {
  if (!valid) {
    return (
      <div className="cl-state" role="alert">
        <h2>Invalid report address</h2>
        <p>Open this report from the class dashboard.</p>
      </div>
    );
  }

  if (resource.loading) {
    return (
      <div className="cl-state" role="status">
        <h2>Loading report…</h2>
      </div>
    );
  }

  if (resource.error) {
    return (
      <div className="cl-state">
        <RequestError error={resource.error} retry={resource.reload} />
      </div>
    );
  }

  if (!resource.data) {
    return (
      <div className="cl-state" role="status">
        <p>No report was returned.</p>
      </div>
    );
  }

  return children(resource.data);
}

function Summary({ items }) {
  return (
    <section className="cl-summary" aria-label="Report summary">
      {items.map(([label, value]) => (
        <div className="cl-stat" key={label}>
          <span>{label}</span>
          <strong>{value}</strong>
        </div>
      ))}
    </section>
  );
}

// The Excel exports are built by the backend from the same reports.
function ExcelButton({ file, path, name }) {
  return (
    <button
      type="button"
      className="cl-button"
      disabled={file.busy}
      onClick={() => void file.download(path, name)}
    >
      {file.busy ? "Preparing…" : "Export Excel"}
    </button>
  );
}

function SessionReport({ report, classId, onCorrected, refreshing }) {
  const backTo = `/app/classes/${classId}`;

  /*
   * The backend determines whether the response includes everybody's
   * results or only the caller's results.
   */
  if (report.view === "host") {
    return (
      <HostResults
        report={report}
        backTo={backTo}
        backLabel="Class dashboard"
        exportPath={`/classes/${classId}/sessions/${report.session_id}/export.xlsx`}
        exportName={`class-${classId}-session-${report.session_id}-results.xlsx`}
        exportLabel="Export Excel"
        onCorrected={onCorrected}
        refreshing={refreshing}
      />
    );
  }

  if (report.view === "participant") {
    return (
      <ParticipantResults
        report={report}
        backTo={backTo}
        backLabel="Class dashboard"
      />
    );
  }

  return (
    <p className="cl-section-note" role="alert">
      The server returned an unsupported report view.
    </p>
  );
}

export function ClassSessionReportPage() {
  const { classId, sessionId } = useParams();
  const valid = validId(classId) && validId(sessionId);

  const resource = useResource(
    valid ? `/classes/${classId}/sessions/${sessionId}/results` : null,
  );

  return (
    <ReportRequest valid={valid} resource={resource}>
      {(report) => (
        <SessionReport
          report={report}
          classId={classId}
          onCorrected={resource.refresh}
          refreshing={resource.refreshing}
        />
      )}
    </ReportRequest>
  );
}

const HISTORY_COLUMNS = ["", "", "cl-num", "", "cl-top-col", "cl-go-cell"];

// Every completed presentation of one quiz, in the same rows as the class
// page's Presentations tab. Each row opens that presentation's results.
function QuizReport({ report, classId }) {
  // For "attended / students"; read once, not polled.
  const dashboard = useResource(`/classes/${classId}/dashboard`);
  const studentCount = dashboard.data?.student_count ?? null;
  const total = report.sessions.length;

  return (
    <>
      <Summary
        items={[
          ["Completed presentations", number(report.session_count)],
          ["Total participations", number(report.participant_count)],
          ["Average points", number(report.average_score)],
        ]}
      />

      <ReportTable
        caption="Presentation history"
        noun="presentation"
        tableClass="cl-rows"
        columnClasses={HISTORY_COLUMNS}
        headers={["Date", "Presentation", "Attended", "Avg score", "Top score", ""]}
        emptyTitle="No presentations yet"
        emptyText="No completed presentations are available."
        rows={report.sessions.map((session, index) => {
          const to = sessionUrl(classId, session.session_id);
          return {
            key: session.session_id,
            text: `${session.quiz_title} ${session.host_name}`,
            to,
            leadClass: "cl-date",
            cells: [
              <DateBlock value={session.started_at} />,
              <span className="cl-quiz-cell">
                <Link className="cl-quiz-name" to={to}>
                  {session.quiz_title}
                </Link>
                <small>
                  P{total - index} · hosted by {session.host_name}
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
              <GoLink to={to} label={`Results for ${session.quiz_title}`} />,
            ],
          };
        })}
      />
    </>
  );
}

export function ClassQuizReportPage() {
  const { classId, quizId } = useParams();
  const valid = validId(classId) && validId(quizId);

  const resource = useResource(
    valid ? `/classes/${classId}/quizzes/${quizId}/results` : null,
  );
  const file = useFileDownload();

  return (
    <ReportFrame
      classId={classId}
      title={resource.data?.title || "Quiz report"}
      actions={
        // Class-wide exports are for the class's organizers only.
        resource.data?.view === "organizer" && (
          <ExcelButton
            file={file}
            path={`/classes/${classId}/quizzes/${quizId}/export.xlsx`}
            name={`class-${classId}-quiz-${quizId}-results.xlsx`}
          />
        )
      }
      error={file.error}
    >
      <ReportRequest valid={valid} resource={resource}>
        {(report) => <QuizReport report={report} classId={classId} />}
      </ReportRequest>
    </ReportFrame>
  );
}

function StudentReport({ report, classId }) {
  const navigate = useNavigate();

  return (
    <>
      <Summary
        items={[
          ["Sessions played", number(report.session_count)],
          ["Average points", number(report.average_score)],
          ["Total points", number(report.total_points)],
          [
            "Attendance",
            report.attendance_rate == null
              ? "—"
              : `${Math.round(report.attendance_rate * 100)}%`,
          ],
          ["Correct answers", number(report.correct_count)],
          ["Incorrect / unanswered", number(report.incorrect_count)],
          ["Class average", number(report.class_average)],
        ]}
      />

      <p className="cl-section-note">
        Average points exclude sessions the student did not play. Unanswered
        questions count as incorrect. Class-wide figures are shown only when the
        backend grants access.
      </p>

      <div className="cl-table-wrap">
        <table className="cl-table">
          <caption className="cl-sr">Student session history</caption>

          <thead>
            <tr>
              <th scope="col">Date</th>
              <th scope="col">Quiz</th>
              <th scope="col">Participation</th>
              <th scope="col">Points</th>
              <th scope="col">Correct</th>
              <th scope="col">Incorrect</th>
              <th scope="col">Rank</th>
              <th scope="col">Report</th>
            </tr>
          </thead>

          <tbody>
            {report.sessions.map((session) => (
              // A played session opens its results from anywhere on the row.
              <tr
                key={session.session_id}
                {...(session.played &&
                  rowLink(navigate, sessionUrl(classId, session.session_id)))}
              >
                <td>{date(session.started_at)}</td>
                <td>{session.quiz_title}</td>
                <td>{session.played ? "Played" : "Absent"}</td>
                <td>{number(session.points)}</td>
                <td>{number(session.correct)}</td>
                <td>{number(session.incorrect)}</td>
                <td>{number(session.rank)}</td>
                <td>
                  {session.played ? (
                    <Link to={sessionUrl(classId, session.session_id)}>
                      Session report →
                    </Link>
                  ) : (
                    "—"
                  )}
                </td>
              </tr>
            ))}

            {report.sessions.length === 0 && (
              <tr>
                <td colSpan={8}>
                  <div className="cl-state">
                    <p>No completed sessions are available in this class.</p>
                  </div>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}

export function ClassStudentReportPage() {
  const { classId, accountId } = useParams();
  const valid = validId(classId) && validId(accountId);

  const resource = useResource(
    valid ? `/classes/${classId}/students/${accountId}/results` : null,
  );
  const file = useFileDownload();

  return (
    <ReportFrame
      classId={classId}
      title={
        resource.data
          ? `${resource.data.display_name} — report`
          : "Student report"
      }
      actions={
        // Anyone who can open this report may export it.
        resource.data && (
          <ExcelButton
            file={file}
            path={`/classes/${classId}/students/${accountId}/export.xlsx`}
            name={`class-${classId}-student-${accountId}-results.xlsx`}
          />
        )
      }
      error={file.error}
    >
      <ReportRequest valid={valid} resource={resource}>
        {(report) => <StudentReport report={report} classId={classId} />}
      </ReportRequest>
    </ReportFrame>
  );
}
