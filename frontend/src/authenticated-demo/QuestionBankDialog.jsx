import { useEffect, useMemo, useRef, useState } from "react";
import { useApi } from "./rest";
import RequestError from "./RequestError";
import { toEditorQuestion, unsupportedReason } from "./questionBankModel";

export default function QuestionBankDialog({ open, classId, onClose, onAdd }) {
  const api = useApi();
  const onCloseRef = useRef(onClose);
  const csvInputRef = useRef(null);
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

  // Rows the editor can't represent (e.g. several correct answers) are shown
  // as invalid so they can't be ticked and don't block the other rows.
  const csvRows = useMemo(() => (preview?.rows ?? []).map((row) => {
    const reason = row.valid ? unsupportedReason(row.question) : null;
    return reason ? { ...row, valid: false, errors: [reason] } : row;
  }), [preview]);
  const validCsvRows = useMemo(() => csvRows.filter((row) => row.valid), [csvRows]);
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
      onAdd(items.filter((item) => selected.has(item.bank_question_id)).map(toEditorQuestion));
      closeDialog();
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
      setCsvSelected(new Set(result.rows
        .filter((row) => row.valid && !unsupportedReason(row.question))
        .map((row) => row.row_number)));
    } catch (failure) { setError(failure); setPreview(null); }
    finally { setBusy(false); }
  }

  async function importCsv() {
    const chosen = validCsvRows.filter((row) => csvSelected.has(row.row_number));
    if (!chosen.length) return;
    setBusy(true); setError(null);
    try {
      onAdd(chosen.map((row) => toEditorQuestion(row.question)));
      closeDialog();
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
          <button type="button" onClick={() => csvInputRef.current?.click()} disabled={busy}>Import CSV</button>
          <input
            ref={csvInputRef}
            className="ui-sr"
            type="file"
            accept=".csv,text/csv"
            onChange={(event) => void readCsv(event.target.files?.[0])}
          />
        </div>
        <RequestError error={error} />
        {preview && <section className="qb-csv-preview" aria-label={`CSV preview for ${csvFileName}`}>
          <div className="qb-csv-status">
            <strong>{validCsvRows.length} valid</strong>
            <span>{csvRows.length - validCsvRows.length} invalid</span>
          </div>
          {csvRows.map((row) => row.valid ? (
            <label className="qb-csv-row" key={row.row_number}>
              <input type="checkbox" checked={csvSelected.has(row.row_number)} onChange={() => toggle(setCsvSelected, row.row_number)} />
              <span className="qb-csv-check" aria-hidden="true">✓</span>
              <span><small>Row {row.row_number}</small><strong>{row.question.question_text}</strong></span>
            </label>
          ) : <p className="qb-csv-error" role="alert" key={row.row_number}>Row {row.row_number}: {row.errors.join(" ")}</p>)}
          <button type="button" className="qb-btn qb-btn-orange" disabled={!csvSelected.size || busy} onClick={importCsv}>Import selected ({csvSelected.size})</button>
        </section>}
        <div className="qb-bank-list" aria-busy={loading}>
          {loading ? <p>Loading questions…</p> : items.length ? items.map((item) => {
            const reason = unsupportedReason(item);
            return (
            <article
              key={item.bank_question_id}
              className={`qb-bank-row${selected.has(item.bank_question_id) ? " is-selected" : ""}${reason ? " is-unsupported" : ""}`}
            >
              <label className="qb-bank-select">
                <input
                  type="checkbox"
                  checked={selected.has(item.bank_question_id)}
                  disabled={Boolean(reason)}
                  onChange={() => toggle(setSelected, item.bank_question_id)}
                />
                <span className="qb-bank-check" aria-hidden="true">✓</span>
                <span className="qb-bank-copy">
                  <strong>{item.question_text}</strong>
                  {reason && <small className="qb-bank-unsupported">{reason}</small>}
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
            );
          }) : <p>No matching questions.</p>}
        </div>
        <button className="qb-btn qb-btn-blue" type="button" disabled={!selected.size || busy} onClick={addSelected}>Add selected ({selected.size})</button>
      </section>
    </div>
  );
}
