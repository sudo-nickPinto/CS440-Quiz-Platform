export const SINGLE_CORRECT_REQUIRED =
  "This quiz editor supports exactly one correct answer per question.";

// Columns must match the backend CSV template so an export can be re-imported.
export const CSV_COLUMNS = [
  "question_text", "explanation", "choice_a", "choice_b", "choice_c",
  "choice_d", "correct_choices",
];

// Returns why a bank/CSV question can't be added to this editor, or null.
export function unsupportedReason(item) {
  const correct = item.choices.filter((choice) => choice.is_correct).length;
  return correct === 1 ? null : SINGLE_CORRECT_REQUIRED;
}

export function toEditorQuestion(item) {
  if (unsupportedReason(item)) throw new Error(SINGLE_CORRECT_REQUIRED);

  return {
    id: crypto.randomUUID(),
    text: item.question_text,
    explanation: item.explanation ?? "",
    options: item.choices.map((choice) => choice.choice_text),
    correct: item.choices.findIndex((choice) => choice.is_correct),
    // Reused content inherits the destination quiz's current defaults.
    limit: null,
    basePoints: 1000,
  };
}

function csvCell(value) {
  let text = value == null ? "" : String(value);
  // Same spreadsheet-formula guard the backend export uses.
  if (/^[=+\-@]/.test(text)) text = `'${text}`;
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

const CSV_CHOICE_LIMIT = 4;

// Serializes a saved quiz's questions (API shape) in the import template.
// Several correct answers are written as "A|C", which the importer reads.
export function quizQuestionsToCsv(questions) {
  const ordered = [...questions].sort((a, b) => a.question_order - b.question_order);
  const tooMany = ordered.filter((question) => question.choices.length > CSV_CHOICE_LIMIT);
  if (tooMany.length) {
    throw new Error(
      `CSV export supports at most ${CSV_CHOICE_LIMIT} choices per question; `
      + `${tooMany.length} question(s) in this quiz have more.`,
    );
  }
  const rows = ordered.map((question) => {
    const choices = [...question.choices].sort((a, b) => a.choice_order - b.choice_order);
    return [
      question.question_text,
      question.explanation,
      ...Array.from({ length: CSV_CHOICE_LIMIT }, (_, index) => choices[index]?.choice_text ?? ""),
      choices.map((choice, index) => choice.is_correct ? String.fromCharCode(65 + index) : null)
        .filter(Boolean).join("|"),
    ];
  });
  return [CSV_COLUMNS, ...rows].map((row) => row.map(csvCell).join(",")).join("\r\n") + "\r\n";
}

// Downloads a saved quiz's questions as `<quiz-title>-questions.csv`.
export function downloadQuizQuestionsCsv(title, questions) {
  const text = quizQuestionsToCsv(questions);
  const slug = (title ?? "").trim().toLowerCase()
    .replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  const url = URL.createObjectURL(new Blob([text], { type: "text/csv" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = `${slug || "quiz"}-questions.csv`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}
