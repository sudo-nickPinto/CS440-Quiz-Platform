import { Link } from "react-router";
import "./quiz-cards.css";

export default function QuizCard({
  title,
  to,
  state,
  status,
  archived = false,
  headline,
  children,
  actions,
  linkLabel = "View quiz",
}) {
  return (
    <article className={`qc-card${archived ? " qc-archived" : ""}`}>
      <div className="qc-banner">
        <span className="qc-status">{status}</span>
        <strong className="qc-headline">{headline}</strong>
      </div>
      <div className="qc-body">
        {/* No `to` means the viewer can't open the quiz page: plain title. */}
        <h2>
          {to ? (
            <Link to={to} state={state}>
              {title}
            </Link>
          ) : (
            title
          )}
        </h2>
        <div className="qc-meta">{children}</div>
      </div>
      {(to || actions) && (
        <div className="qc-footer">
          {to && (
            <Link to={to} state={state}>
              {linkLabel} <span aria-hidden="true">→</span>
            </Link>
          )}
          {actions}
        </div>
      )}
    </article>
  );
}
