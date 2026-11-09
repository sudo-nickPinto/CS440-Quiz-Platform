import "./quiz-start-countdown.css";

export default function QuizStartCountdown({ number, onCancel, busy }) {
  return (
    <section className="lv-start-countdown" aria-label="Quiz starting">
      <p className="lv-eyebrow">Get ready!</p>
      <div role="status" aria-live="polite" aria-atomic="true">
        <span key={number} className={`lv-start-number lv-start-number-${number}`}>
          {number}
        </span>
      </div>
      <p>The first question is coming up.</p>
      {onCancel && (
        <button type="button" className="qb-btn qb-btn-paper" onClick={onCancel} disabled={busy}>
          Back to lobby
        </button>
      )}
    </section>
  );
}
