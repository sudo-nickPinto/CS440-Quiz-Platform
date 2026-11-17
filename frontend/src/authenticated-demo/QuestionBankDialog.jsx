import { useEffect, useMemo, useRef, useState } from "react";
import { useApi } from "./rest";
import RequestError from "./RequestError";
import { toEditorQuestion } from "./questionBankModel";

export default function QuestionBankDialog({ open, classId, quizId, onClose, onAdd, onReload }) {
  const api = useApi();
  const onCloseRef = useRef(onClose);
  const [scope, setScope] = useState("class");
  const [search, setSearch] = useState("");
  const [items, setItems] = useState([]);
  const [selected, setSelected] = useState(new Set());
  const [expanded, setExpanded] = useState(new Set());
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [preview, setPreview] = useState(null);
  const [csvFileName, setCsvFileName] = useState("");
  const [csvSelected, setCsvSelected] = useState(new Set());

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  function resetDialog() {
    setSelected(new Set());
    setExpanded(new Set());
    setPreview(null);
    setCsvFileName("");
    setCsvSelected(new Set());
    setError(null);
  }

  function closeDialog() {
    resetDialog();
    onCloseRef.current();
  }

  useEffect(() => {
    if (!open) return undefined;
    const closeOnEscape = (event) => {
      if (event.key !== "Escape") return;
      setSelected(new Set());
      setExpanded(new Set());
      setPreview(null);
      setCsvFileName("");
      setCsvSelected(new Set());
      setError(null);
      onCloseRef.current();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const timer = window.setTimeout(async () => {
      setLoading(true); setError(null);
      try {
        const result = await api(`/classes/${classId}/question-bank?scope=${scope}&search=${encodeURIComponent(search)}&page_size=100`);
        setItems(result.items);
      } catch (failure) { setError(failure); }
      finally { setLoading(false); }
    }, 200);
    return () => window.clearTimeout(timer);
  }, [api, classId, open, scope, search]);

  const validCsvRows = useMemo(() => preview?.rows.filter((row) => row.valid) ?? [], [preview]);
  if (!open) return null;

  function toggle(setter, id) {
    setter((value) => {
      const next = new Set(value);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  async function addSelected() {
    if (!selected.size) return;
    setBusy(true); setError(null);
    try {
      if (quizId) {
        await api(`/classes/${classId}/quizzes/${quizId}/questions/from-bank`, {
          method: "POST", body: JSON.stringify({ bank_question_ids: [...selected] }),
        });
        onReload?.(); closeDialog();
      } else {
        onAdd(items.filter((item) => selected.has(item.bank_question_id)).map(toEditorQuestion));
        closeDialog();
      }
    } catch (failure) { setError(failure); }
    finally { setBusy(false); }
  }

  async function readCsv(file) {
    if (!file) return;
    setCsvFileName(file.name);
    const text = await file.text(); setBusy(true); setError(null);
    try {
      const result = await api(`/classes/${classId}/question-bank/csv/preview`, {
        method: "POST", body: JSON.stringify({ csv_text: text }),
      });
      setPreview(result);
      setCsvSelected(new Set(result.rows.filter((row) => row.valid).map((row) => row.row_number)));
    } catch (failure) { setError(failure); setPreview(null); }
    finally { setBusy(false); }
  }

  async function importCsv() {
    const chosen = validCsvRows.filter((row) => csvSelected.has(row.row_number));
    if (!chosen.length) return;
    setBusy(true); setError(null);
    try {
      if (quizId) {
        await api(`/classes/${classId}/quizzes/${quizId}/questions/csv`, {
          method: "POST",
          body: JSON.stringify({
            rows: chosen.map(({ row_number, question }) => ({ row_number, question })),
            save_unselected_to_bank: false,
            bank_only_rows: [],
          }),
        });
        onReload?.(); closeDialog();
      } else {
        onAdd(chosen.map((row) => toEditorQuestion({ ...row.question, question_text: row.question.question_text })));
        closeDialog();
      }
    } catch (failure) { setError(failure); }
    finally { setBusy(false); }
  }

  async function exportCsv() {
    setBusy(true); setError(null);
    try {
      const ids = selected.size ? `&${[...selected].map((id) => `ids=${id}`).join("&")}` : "";
      const text = await api(`/classes/${classId}/question-bank/export.csv?scope=${scope}${ids}`);
      const url = URL.createObjectURL(new Blob([text], { type: "text/csv" }));
      const link = document.createElement("a"); link.href = url; link.download = "question-bank.csv";
      document.body.appendChild(link); link.click(); link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 0);
    } catch (failure) { setError(failure); }
    finally { setBusy(false); }
  }

  return (
    <div className="qb-modal-backdrop" role="presentation" onMouseDown={(e) => e.target === e.currentTarget && closeDialog()}>
      <section className="qb-bank" role="dialog" aria-modal="true" aria-labelledby="bank-title">
        <header><div><small>Reusable content</small><h2 id="bank-title">Question bank</h2></div><button type="button" onClick={closeDialog} aria-label="Close">×</button></header>
        <div className="qb-bank-tools">
          <input aria-label="Search questions" placeholder="Search questions…" value={search} onChange={(e) => setSearch(e.target.value)} />
          <select aria-label="Question source" value={scope} onChange={(e) => setScope(e.target.value)}>
            <option value="class">Current class + mine</option><option value="mine">My questions across classes</option>
          </select>
          <button type="button" onClick={exportCsv} disabled={busy}>Export CSV</button>
        </div>
        <RequestError error={error} />
        <div className="qb-bank-list" aria-busy={loading}>
          {loading ? <p>Loading questions…</p> : items.length ? items.map((item) => (
            <article
              key={item.bank_question_id}
              className={`qb-bank-row${selected.has(item.bank_question_id) ? " is-selected" : ""}`}
            >
              <label className="qb-bank-select">
                <input
                  type="checkbox"
                  checked={selected.has(item.bank_question_id)}
                  onChange={() => toggle(setSelected, item.bank_question_id)}
                />
                <span className="qb-bank-check" aria-hidden="true">✓</span>
                <span className="qb-bank-copy">
                  <strong>{item.question_text}</strong>
                </span>
              </label>
              <button
                type="button"
                className="qb-bank-expand"
                aria-expanded={expanded.has(item.bank_question_id)}
                aria-controls={`bank-choices-${item.bank_question_id}`}
                aria-label={`${expanded.has(item.bank_question_id) ? "Hide" : "Show"} choices for ${item.question_text}`}
                onClick={() => toggle(setExpanded, item.bank_question_id)}
              >
                <span aria-hidden="true" />
              </button>
              {expanded.has(item.bank_question_id) && (
                <ol className="qb-bank-choices" id={`bank-choices-${item.bank_question_id}`}>
                  {item.choices.map((choice, index) => (
                    <li key={`${item.bank_question_id}-${index}`} className={choice.is_correct ? "is-correct" : ""}>
                      <span>{String.fromCharCode(65 + index)}</span>
                      <strong>{choice.choice_text}</strong>
                      {choice.is_correct && <small>Correct</small>}
                    </li>
                  ))}
                </ol>
              )}
            </article>
          )) : <p>No matching questions.</p>}
        </div>
        <button className="qb-btn qb-btn-blue" type="button" disabled={!selected.size || busy} onClick={addSelected}>Add selected ({selected.size})</button>

        <details className="qb-csv">
          <summary>Import CSV</summary>
          <p className="qb-csv-help">Columns: question_text, explanation, choice_a–choice_d, correct_choices.</p>
          <label className="qb-csv-file">
            <span>Choose CSV</span>
            <strong>{csvFileName || "No file selected"}</strong>
            <input type="file" accept=".csv,text/csv" onChange={(e) => readCsv(e.target.files?.[0])} />
          </label>
          {preview && <div className="qb-csv-preview">
            <div className="qb-csv-status">
              <strong>{preview.valid_count} valid</strong>
              <span>{preview.invalid_count} invalid</span>
            </div>
            {preview.rows.map((row) => row.valid ? (
              <label className="qb-csv-row" key={row.row_number}>
                <input type="checkbox" checked={csvSelected.has(row.row_number)} onChange={() => toggle(setCsvSelected, row.row_number)} />
                <span className="qb-csv-check" aria-hidden="true">✓</span>
                <span><small>Row {row.row_number}</small><strong>{row.question.question_text}</strong></span>
              </label>
            ) : <p className="qb-csv-error" role="alert" key={row.row_number}>Row {row.row_number}: {row.errors.join(" ")}</p>)}
            <button type="button" className="qb-btn qb-btn-orange" disabled={!csvSelected.size || busy} onClick={importCsv}>Import selected ({csvSelected.size})</button>
          </div>}
        </details>
      </section>
    </div>
  );
}
