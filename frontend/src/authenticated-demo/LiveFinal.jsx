import { useEffect, useState } from "react";
import { Link } from "react-router";

// End-of-quiz screens from presenter-flow-main.html (podium + top 5) and
// participant-flow-main.html ("Quiz complete · Great job!"). They read the
// session_ended payload; the buttons lead to the saved report pages.

const fmt = (value) => Number(value ?? 0).toLocaleString();

// Raise the podium a moment after the screen appears.
function useRaised() {
  const [raised, setRaised] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => setRaised(true), 120);
    return () => window.clearTimeout(timer);
  }, []);

  return raised;
}

export function HostFinal({ final, title, totalQuestions, sessionId }) {
  const raised = useRaised();
  const standings = [...(final.standings ?? [])].sort(
    (a, b) => a.final_rank - b.final_rank,
  );
  const top = standings.slice(0, 5);

  // Podium order on screen: 2nd, 1st, 3rd
  const podium = [standings[1], standings[0], standings[2]];
  const heights = ["58%", "80%", "40%"];

  return (
    <section className="lv-final" aria-labelledby="final-title">
      <p className="lv-eyebrow">
        {title} · {totalQuestions} questions · {standings.length}{" "}
        {standings.length === 1 ? "player" : "players"}
      </p>
      <h1 id="final-title">Final results</h1>

      {standings.length ? (
        <div className="lv-final-grid">
          <div className="lv-podium" aria-hidden="true">
            {podium.map((row, index) =>
              row ? (
                <div
                  key={row.session_participant_id}
                  className={
                    `lv-podium-col p${row.final_rank}` + (raised ? " is-up" : "")
                  }
                  style={{ "--h": heights[index], "--i": index }}
                >
                  <div className="lv-podium-name">
                    <strong>{row.display_name}</strong>
                    <span>{fmt(row.total_score)} pts</span>
                  </div>
                  <div className="lv-podium-block">
                    <span className="lv-podium-rank">{row.final_rank}</span>
                  </div>
                </div>
              ) : (
                <div key={`empty-${index}`} className="lv-podium-col is-empty" />
              ),
            )}
          </div>

          <div className="lv-final-board">
            <p className="lv-eyebrow">Top {top.length}</p>
            <ol className="lv-board">
              {top.map((row, index) => (
                <li key={row.session_participant_id} style={{ "--i": index }}>
                  <span className="lv-rank">{row.final_rank}</span>
                  <strong>{row.display_name}</strong>
                  <span className="lv-pts">{fmt(row.total_score)} pts</span>
                </li>
              ))}
            </ol>
          </div>
        </div>
      ) : (
        <p className="lv-final-empty">Nobody answered in this session.</p>
      )}

      <div className="lv-actions">
        <Link className="qb-btn qb-btn-paper" to="/app/dashboard/present">
          Back to dashboard
        </Link>
        <Link className="qb-btn" to={`/app/results/host/${sessionId}`}>
          View full results →
        </Link>
      </div>
    </section>
  );
}

export function ParticipantFinal({ final, totalQuestions, sessionId }) {
  const me = final.me;

  return (
    <section className="lv-complete" aria-labelledby="complete-title">
      <div className="lv-trophy" aria-hidden="true">
        ★
      </div>
      <p className="lv-eyebrow">Quiz complete</p>
      <h1 id="complete-title">{me ? "Great job!" : "Thanks for playing!"}</h1>

      {me && (
        <>
          <div className="lv-big-score">
            <strong>
              {me.correct_count} <small>/</small> {totalQuestions}
            </strong>
            <span>Correct answers</span>
          </div>

          <div className="lv-stat-row">
            <div className="lv-stat">
              <span>Final rank</span>
              <strong>#{me.final_rank}</strong>
            </div>
            <div className="lv-stat">
              <span>Points</span>
              <strong>{fmt(me.total_score)}</strong>
            </div>
          </div>

          <p className="lv-sub">
            Your recorded result is {me.correct_count} out of {totalQuestions}{" "}
            correct.
          </p>
        </>
      )}

      <div className="lv-stack-actions">
        <Link className="qb-btn" to={`/app/results/me/${sessionId}`}>
          See your answers →
        </Link>
        <Link className="qb-btn qb-btn-paper" to="/app/dashboard/participate">
          Back to dashboard
        </Link>
      </div>
    </section>
  );
}
