import { useEffect, useMemo, useRef, useState } from "react";
import { useApi } from "./rest";
import RequestError from "./RequestError";
import { exportPlan, visibleQuestions } from "./questionBankExport";
import { useFileDownload } from "./useFileDownload";

const PAGE_SIZE = 100;

// Informational only: these still download (correct_choices like "A|C").
const isMultiCorrect = (item) => item.choices.filter((choice) => choice.is_correct).length > 1;

// The square ✓ box used by the question bank in the quiz editor. The real
// checkbox is visually hidden; "mixed" draws a dash for a partly ticked group.
function Check({ checked, mixed = false, label, children, className = "", ...props }) {
  const ref = useRef(null);
  useEffect(() => {
    if (ref.current) ref.current.indeterminate = mixed;
  }, [mixed]);
  return (
    <label className={`qbx-check ${checked ? "is-on" : ""} ${className}`.trim()}>
      <input ref={ref} type="checkbox" className="ui-sr" checked={checked} aria-label={label} {...props} />
      <span className={`qbx-box${mixed ? " is-mixed" : ""}`} aria-hidden="true">{mixed ? "–" : "✓"}</span>
      {children}
    </label>
  );
}

// "ALL QUIZZES ▾": a site-styled pop-up list (like Time per question), not
// the browser's own select. dismissPopovers closes it on a pick, an outside
// click or Escape.
function QuizPicker({ quizzes, value, onChange, disabled }) {
  const chosen = quizzes.find((quiz) => quiz.quiz_id === value);
  return (
    <details className="qb-pop qbx-pick-quiz">
      <summary
        aria-label={`Quiz: ${chosen ? chosen.title : "All quizzes"}. Change`}
        aria-disabled={disabled || undefined}
        onClick={(event) => disabled && event.preventDefault()}
      >
        <span className="qbx-pick-label">{chosen ? chosen.title : "All quizzes"}</span>
        <span aria-hidden="true">▾</span>
      </summary>
      <div className="qbx-pick-panel" role="group" aria-label="Quiz">
        <button type="button" className="ui-opt" aria-pressed={value == null} onClick={() => onChange(null)}>
          All quizzes
        </button>
        {quizzes.map((quiz) => (
          <button
            key={quiz.quiz_id}
            type="button"
            className="ui-opt"
            aria-pressed={quiz.quiz_id === value}
            onClick={() => onChange(quiz.quiz_id)}
          >
            {quiz.title}
            <small>{quiz.question_count}</small>
          </button>
        ))}
      </div>
    </details>
  );
}

// Every bank question of one class, a page at a time until done.
async function loadClassQuestions(api, classId) {
  const items = [];
  for (let page = 1; ; page += 1) {
    const result = await api(
      `/question-bank/items?class_ids=${classId}&page=${page}&page_size=${PAGE_SIZE}`,
    );
    items.push(...result.items);
    if (items.length >= result.pagination.total_items || !result.items.length) return items;
  }
}

/*
 * The class dashboard's question bank: download this class's questions as
 * CSV. Every question starts ticked; the quiz picker and search narrow what's
 * shown, and the ticked questions shown are what downloads.
 */
export default function QuestionBankExportDialog({ classId, className, onClose }) {
  const api = useApi();
  const dialogRef = useRef(null);
  // Escape first closes an open quiz picker (dismissPopovers does that before
  // the dialog's cancel event), and only a second Escape closes the pop-up.
  const pickerWasOpen = useRef(false);
  const [items, setItems] = useState(null);
  const [quizzes, setQuizzes] = useState([]);
  const [quizId, setQuizId] = useState(null);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState(new Set());
  const [error, setError] = useState(null);
  const file = useFileDownload();

  useEffect(() => {
    const dialog = dialogRef.current;
    if (dialog && !dialog.open) dialog.showModal();
  }, []);

  useEffect(() => {
    let live = true;
    Promise.all([api("/question-bank/sources"), loadClassQuestions(api, classId)])
      .then(([sources, questions]) => {
        if (!live) return;
        const course = sources.courses.find((entry) => entry.class_id === classId);
        setQuizzes(course?.quizzes ?? []);
        setItems(questions);
        setSelected(new Set(questions.map((question) => question.bank_question_id)));
      })
      .catch((failure) => {
        if (live) { setError(failure); setItems([]); }
      });
    return () => { live = false; };
  }, [api, classId]);

  const loading = items === null;
  const shown = useMemo(() => visibleQuestions(items ?? [], { quizId, search }), [items, quizId, search]);
  const ticked = shown.filter((item) => selected.has(item.bank_question_id));
  const quiz = quizzes.find((entry) => entry.quiz_id === quizId) ?? null;
  const plan = exportPlan({
    className, quiz, search, shown: shown.length, ticked: ticked.length,
    loading, empty: !loading && !items.length,
  });

  function toggle(id) {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  function tickShown(on) {
    setSelected((current) => {
      const next = new Set(current);
      shown.forEach((item) => (on ? next.add(item.bank_question_id) : next.delete(item.bank_question_id)));
      return next;
    });
  }

  function download() {
    void file.download("/question-bank/export.csv", plan.filename, {
      method: "POST",
      body: { class_ids: [classId], bank_question_ids: ticked.map((item) => item.bank_question_id) },
      filename: plan.filename,
    });
  }

  return (
    <dialog
      ref={dialogRef}
      className="cl-dlg cl-dlg-wide qbx"
      aria-labelledby="qbx-title"
      onKeyDownCapture={(event) => {
        if (event.key === "Escape") {
          pickerWasOpen.current = Boolean(dialogRef.current?.querySelector("details[open]"));
        }
      }}
      onCancel={(event) => {
        event.preventDefault();
        if (pickerWasOpen.current) {
          pickerWasOpen.current = false;
          dialogRef.current?.querySelector("details[open]")?.removeAttribute("open");
        } else {
          onClose();
        }
      }}
      onClick={(event) => {
        // A click on the backdrop lands on the <dialog> itself.
        if (event.target === dialogRef.current) onClose();
      }}
    >
      <div className="cl-dlg-top">
        <span id="qbx-title">Question bank · <b>Download as CSV</b></span>
        <button type="button" className="cl-dlg-x" aria-label="Close" onClick={onClose}>×</button>
      </div>

      <div className="cl-add-body">
        <RequestError error={error || file.error} />

        <div className="cl-dlg-row qbx-filters">
          <label className="cl-search">
            <span className="cl-sr">Search questions</span>
            <input
              type="search"
              placeholder="Search questions…"
              value={search}
              disabled={loading}
              onChange={(e) => setSearch(e.target.value)}
            />
          </label>
          <QuizPicker quizzes={quizzes} value={quizId} onChange={setQuizId} disabled={loading} />
        </div>

        <div className="qbx-list-head">
          <Check
            label={`Select all ${shown.length} shown`}
            checked={shown.length > 0 && ticked.length === shown.length}
            mixed={ticked.length > 0 && ticked.length < shown.length}
            disabled={!shown.length}
            onChange={() => tickShown(ticked.length !== shown.length)}
          >
            <span className="qbx-text"><strong>Select all {shown.length} shown</strong></span>
          </Check>
          <span className="qbx-count">
            {loading ? "Loading…" : `${ticked.length} of ${shown.length} ticked`}
          </span>
        </div>

        <div className="qbx-list" aria-busy={loading}>
          {shown.length ? shown.map((item) => (
            <article
              key={item.bank_question_id}
              className={`qbx-row${selected.has(item.bank_question_id) ? " is-selected" : ""}`}
            >
              <Check
                label={item.question_text}
                className="qbx-pick"
                checked={selected.has(item.bank_question_id)}
                onChange={() => toggle(item.bank_question_id)}
              >
                <span className="qbx-copy">
                  <strong>{item.question_text}</strong>
                  {isMultiCorrect(item) && (
                    <small
                      className="qbx-tag"
                      title="More than one correct answer. It downloads as e.g. A|C."
                    >
                      Multi-correct
                    </small>
                  )}
                </span>
              </Check>
            </article>
          )) : (
            <p className="qbx-empty">
              {loading ? "Loading questions…" : items.length ? "No matching questions." : "No questions yet. Questions are added to the bank when quizzes are written in this class."}
            </p>
          )}
        </div>
      </div>

      <div className="cl-dlg-foot">
        <span aria-live="polite">{plan.disabled ? plan.summary : <>You’ll download: <b>{plan.summary}</b></>}</span>
        <button
          type="button"
          className="cl-add-one"
          disabled={plan.disabled || file.busy}
          onClick={download}
        >
          {file.busy ? "Preparing…" : plan.button}
        </button>
      </div>
    </dialog>
  );
}
