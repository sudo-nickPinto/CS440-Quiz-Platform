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

// Serializes the editor's current questions (including unsaved edits).
export function editorQuestionsToCsv(questions) {
  const rows = questions.map((question) => {
    const choices = ["a", "b", "c", "d"].map((_, index) => question.options[index] ?? "");
    return [
      question.text,
      question.explanation,
      ...choices,
      String.fromCharCode(65 + question.correct),
    ];
  });
  return [CSV_COLUMNS, ...rows].map((row) => row.map(csvCell).join(",")).join("\r\n") + "\r\n";
}
