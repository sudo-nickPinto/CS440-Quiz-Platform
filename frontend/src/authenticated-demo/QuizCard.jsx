import { Link } from "react-router";
import "./quiz-cards.css";

// wholeCard: the title link is stretched over the card (see .qc-card-link in
// quiz-cards.css), so a click anywhere opens `to`. Buttons and menus on the
// card sit above that link and keep working. There's no separate footer link.
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
  wholeCard = false,
}) {
  const clickable = Boolean(to) && wholeCard;
  const footerLink = Boolean(to) && !wholeCard;

  return (
    <article
      className={
        "qc-card" +
        (archived ? " qc-archived" : "") +
        (clickable ? " is-clickable" : "")
      }
    >
      <div className="qc-banner">
        <span className="qc-status">{status}</span>
        <strong className="qc-headline">{headline}</strong>
      </div>
      <div className="qc-body">
        {/* No `to` means the viewer can't open the quiz page: plain title. */}
        <h2>
          {to ? (
            <Link
              to={to}
              state={state}
              className={clickable ? "qc-card-link" : undefined}
            >
              {title}
            </Link>
          ) : (
            title
          )}
        </h2>
        <div className="qc-meta">{children}</div>
      </div>
      {(footerLink || actions) && (
        <div className="qc-footer">
          {footerLink && (
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
