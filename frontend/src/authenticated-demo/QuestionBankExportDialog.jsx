import { useEffect, useMemo, useRef, useState } from "react";
import { useApi } from "./rest";
import RequestError from "./RequestError";
import { exportPlan, saveCsvFile } from "./questionBankExport";

const PAGE_SIZE = 100;

// The square ✓ box used by the question bank in the quiz editor. The real checkbox is
// visually hidden; "mixed" draws a dash for a partly selected group.
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

/*
 * The admin dashboard's question bank: download questions as CSV from every
 * course, some courses, one quiz, or exactly the ticked questions.
 */
export default function QuestionBankExportDialog({ classId, onClose }) {
  const api = useApi();
  const dialogRef = useRef(null);
  const known = useRef(new Map()); // bank_question_id -> item, for pruning
  const [courses, setCourses] = useState(null);
  const [classIds, setClassIds] = useState(new Set());
  const [quizId, setQuizId] = useState(null);
  const [search, setSearch] = useState("");
  const [loaded, setLoaded] = useState([]);
  const [matching, setMatching] = useState(0);
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState(new Set());
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (dialog && !dialog.open) dialog.showModal();
  }, []);

  // Courses and quizzes. Start with the course the dashboard is open on.
  useEffect(() => {
    let live = true;
    api("/question-bank/sources")
      .then((result) => {
        if (!live) return;
        setCourses(result.courses);
        const here = result.courses.some((course) => course.class_id === classId);
        setClassIds(new Set(here ? [classId] : result.courses.map((course) => course.class_id)));
      })
      .catch((failure) => live && setError(failure));
    return () => { live = false; };
  }, [api, classId]);

  const classKey = [...classIds].sort((a, b) => a - b).join(",");

  // Questions matching the filters; "Show more" adds pages.
  useEffect(() => {
    if (!classKey) return undefined;
    const timer = window.setTimeout(async () => {
      setLoading(true); setError(null);
      try {
        const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
        classKey.split(",").forEach((id) => params.append("class_ids", id));
        if (quizId != null) params.set("quiz_id", String(quizId));
        if (search.trim()) params.set("search", search.trim());
        const result = await api(`/question-bank/items?${params}`);
        result.items.forEach((item) => known.current.set(item.bank_question_id, item));
        setLoaded((current) => (page === 1 ? result.items : [...current, ...result.items]));
        setMatching(result.pagination.total_items);
      } catch (failure) { setError(failure); }
      finally { setLoading(false); }
    }, 200);
    return () => window.clearTimeout(timer);
  }, [api, classKey, quizId, search, page]);

  // With no course ticked nothing is fetched, so show nothing.
  const items = classKey ? loaded : [];
  const total = classKey ? matching : 0;

  const plan = useMemo(() => exportPlan({
    courses: courses ?? [], classIds, quizId, search, selectedIds: selected, matching: total,
  }), [courses, classIds, quizId, search, selected, total]);

  function changeFilters(update) {
    setPage(1);
    update();
  }

  function chooseCourses(next) {
    changeFilters(() => {
      setClassIds(next);
      // A quiz or ticked question from a course that is no longer ticked
      // can't be downloaded, so drop it.
      const quizCourse = courses?.find((course) => course.quizzes.some((quiz) => quiz.quiz_id === quizId));
      if (quizCourse && !next.has(quizCourse.class_id)) setQuizId(null);
      setSelected((current) => new Set([...current].filter(
        (id) => next.has(known.current.get(id)?.source_class_id),
      )));
    });
  }

  function toggleCourse(id) {
    const next = new Set(classIds);
    if (next.has(id)) next.delete(id); else next.add(id);
    chooseCourses(next);
  }

  function toggleQuestion(id) {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  async function download() {
    setBusy(true); setError(null);
    try {
      const text = await api("/question-bank/export.csv", {
        method: "POST", body: JSON.stringify(plan.payload),
      });
      saveCsvFile(text, plan.filename);
    } catch (failure) { setError(failure); }
    finally { setBusy(false); }
  }

  const allCourses = courses?.length > 0 && classIds.size === courses.length;
  const someCourses = classIds.size > 0 && !allCourses;
  const shownSelected = items.filter((item) => selected.has(item.bank_question_id)).length;
  const quizCourses = (courses ?? []).filter(
    (course) => classIds.has(course.class_id) && course.quizzes.length,
  );
  const courseName = (id) => courses?.find((course) => course.class_id === id)?.name;

  return (
    <dialog
      ref={dialogRef}
      className="cl-dlg cl-dlg-wide qbx"
      aria-labelledby="qbx-title"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
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
        <RequestError error={error} />

        {courses === null ? <p className="cl-add-note">Loading courses…</p> : !courses.length ? (
          <p className="cl-dlg-empty">There are no questions in your courses yet. Questions are added to the bank when you write quizzes.</p>
        ) : (
          <>
            <div className="qbx-courses" role="group" aria-label="Courses">
              <Check
                label="Select all courses"
                checked={allCourses}
                mixed={someCourses}
                onChange={() => chooseCourses(allCourses ? new Set() : new Set(courses.map((course) => course.class_id)))}
              >
                <span className="qbx-text"><strong>All courses</strong></span>
              </Check>
              {courses.map((course) => (
                <Check
                  key={course.class_id}
                  label={course.name}
                  checked={classIds.has(course.class_id)}
                  onChange={() => toggleCourse(course.class_id)}
                >
                  <span className="qbx-text">
                    <strong>{course.name}</strong>
                    <small>{course.question_count} {course.question_count === 1 ? "question" : "questions"}{course.archived ? " · archived" : ""}</small>
                  </span>
                </Check>
              ))}
            </div>

            <div className="cl-dlg-row qbx-filters">
              <label className="cl-search">
                <span className="cl-sr">Search questions</span>
                <input
                  type="search"
                  placeholder="Search questions…"
                  value={search}
                  disabled={!classIds.size}
                  onChange={(e) => changeFilters(() => setSearch(e.target.value))}
                />
              </label>
              <label className="cl-sort">
                <span className="cl-sr">Quiz</span>
                <select
                  value={quizId ?? ""}
                  disabled={!classIds.size}
                  onChange={(e) => changeFilters(() => setQuizId(e.target.value ? Number(e.target.value) : null))}
                >
                  <option value="">All quizzes</option>
                  {quizCourses.map((course) => (
                    <optgroup key={course.class_id} label={course.name}>
                      {course.quizzes.map((quiz) => (
                        <option key={quiz.quiz_id} value={quiz.quiz_id}>{quiz.title} ({quiz.question_count})</option>
                      ))}
                    </optgroup>
                  ))}
                </select>
              </label>
            </div>

            <div className="qbx-list-head">
              <Check
                label={`Select all ${items.length} shown`}
                checked={items.length > 0 && shownSelected === items.length}
                mixed={shownSelected > 0 && shownSelected < items.length}
                disabled={!items.length}
                onChange={() => setSelected((current) => {
                  const next = new Set(current);
                  const all = shownSelected === items.length;
                  items.forEach((item) => (all ? next.delete(item.bank_question_id) : next.add(item.bank_question_id)));
                  return next;
                })}
              >
                <span className="qbx-text"><strong>Select all {items.length} shown</strong></span>
              </Check>
              <span className="qbx-count">{loading ? "Loading…" : `${total} ${total === 1 ? "question matches" : "questions match"}`}</span>
            </div>

            <div className="qbx-list" aria-busy={loading}>
              {items.length ? items.map((item) => (
                <article
                  key={item.bank_question_id}
                  className={`qbx-row${selected.has(item.bank_question_id) ? " is-selected" : ""}`}
                >
                  <Check
                    label={item.question_text}
                    className="qbx-pick"
                    checked={selected.has(item.bank_question_id)}
                    onChange={() => toggleQuestion(item.bank_question_id)}
                  >
                    <span className="qbx-copy">
                      <strong>{item.question_text}</strong>
                      {classIds.size > 1 && <small>{courseName(item.source_class_id)}</small>}
                    </span>
                  </Check>
                </article>
              )) : <p>{loading ? "Loading questions…" : classIds.size ? "No matching questions." : "Choose at least one course."}</p>}
              {items.length < total && !loading && (
                <button type="button" className="qbx-more" onClick={() => setPage((value) => value + 1)}>Show more ({total - items.length} left)</button>
              )}
            </div>
          </>
        )}
      </div>

      <div className="cl-dlg-foot">
        <span aria-live="polite">You’ll download: <b>{plan.summary}</b></span>
        <div className="qbx-actions">
          {selected.size > 0 && (
            <button type="button" className="qbx-clear" onClick={() => setSelected(new Set())}>Clear selection</button>
          )}
          <button
            type="button"
            className="cl-add-one"
            disabled={busy || !classIds.size || !plan.count}
            onClick={download}
          >
            {busy ? "Preparing…" : plan.button}
          </button>
        </div>
      </div>
    </dialog>
  );
}
