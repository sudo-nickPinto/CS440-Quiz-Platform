import { useRef, useState } from "react";

// Pieces of the quiz editor from quiz-editor-main.html. They only render
// controls; QuizEditor owns the editor state and passes changes back.

const PRESETS = [10, 20, 30, 45, 60, 90];

// The "TIME PER QUESTION 30s ▾" strip button and each card's time chip.
// `current` is the question's own time, or null when it follows the quiz.
export function TimePicker({
  title,
  label,
  question = false,
  current,
  defaultTime,
  onPick,
  summaryClass = "",
  children,
  footer = null,
}) {
  const ref = useRef(null);
  const [other, setOther] = useState("");
  const [error, setError] = useState("");

  const fallback = Number(defaultTime);
  const presets = question ? PRESETS.filter((t) => t !== fallback) : PRESETS;
  const selected = question ? current : fallback;
  const custom =
    selected != null && !presets.includes(Number(selected))
      ? String(selected)
      : "";

  function pick(seconds) {
    setError("");
    setOther("");
    onPick(seconds);
    if (ref.current) ref.current.open = false;
  }

  function pickOther() {
    const text = other.trim();
    const seconds = Number(text);

    if (!/^\d+$/.test(text) || seconds < 1 || seconds > 65_535) {
      setError("Use a whole number from 1 to 65,535 seconds.");
      return;
    }

    pick(seconds);
  }

  return (
    <details className="qb-pop qe-time" ref={ref}>
      <summary className={summaryClass} aria-label={label}>
        {children}
      </summary>

      <div className="qb-pop-panel qe-time-panel" role="group" aria-label={title}>
        <h4>{title}</h4>

        {question && (
          <button
            type="button"
            className="ui-opt qe-wide"
            aria-pressed={current == null}
            onClick={() => pick(null)}
          >
            Quiz default · {defaultTime}s
            <small>{current == null ? "In use" : ""}</small>
          </button>
        )}

        <div
          className="ui-opts qe-presets"
          style={{ "--n": presets.length }}
          role="group"
          aria-label={question ? "Or its own time" : "Seconds"}
        >
          {presets.map((seconds) => (
            <button
              type="button"
              key={seconds}
              className="ui-opt"
              aria-pressed={Number(selected) === seconds}
              onClick={() => pick(seconds)}
            >
              {seconds}s
            </button>
          ))}
        </div>

        <div className="qe-other">
          <label>
            <span>Other</span>
            <span className={"qe-custom" + (error ? " is-bad" : "")}>
              <input
                inputMode="numeric"
                autoComplete="off"
                placeholder={custom || "e.g. 75"}
                value={other}
                aria-label={`${title}, other number of seconds`}
                onChange={(event) => {
                  setError("");
                  setOther(event.target.value.replace(/\D/g, "").slice(0, 5));
                }}
                onKeyDown={(event) => {
                  // Enter would submit the whole editor form.
                  if (event.key === "Enter") {
                    event.preventDefault();
                    pickOther();
                  }
                }}
              />
              <span aria-hidden="true">sec</span>
            </span>
          </label>

          <button
            type="button"
            className="ui-opt"
            data-keep-open
            onClick={pickOther}
          >
            Set
          </button>
        </div>

        {error && (
          <p className="qe-err" role="alert">
            {error}
          </p>
        )}

        {footer}
      </div>
    </details>
  );
}

// The ⋯ menu in each question card's black title bar.
export function QuestionMenu({ number, first, last, onMove, onDelete }) {
  return (
    <details className="qb-pop qe-menu">
      <summary aria-label={`Question ${number} actions`}>
        <i />
        <i />
        <i />
      </summary>

      <div className="qe-menu-panel" role="menu">
        <button
          type="button"
          role="menuitem"
          disabled={first}
          onClick={() => onMove(-1)}
        >
          ↑ Move up
        </button>
        <button
          type="button"
          role="menuitem"
          disabled={last}
          onClick={() => onMove(1)}
        >
          ↓ Move down
        </button>
        <button
          type="button"
          role="menuitem"
          className="ui-danger"
          onClick={onDelete}
        >
          × Delete question
        </button>
      </div>
    </details>
  );
}
