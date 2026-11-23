export function fileSlug(text) {
  return (text ?? "").trim().toLowerCase()
    .replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

const plural = (count, word) => `${count} ${word}${count === 1 ? "" : "s"}`;

// The questions the list shows: this class's bank, narrowed to one quiz
// and/or a search (case-insensitive, anywhere in the question).
export function visibleQuestions(items, { quizId = null, search = "" } = {}) {
  const term = search.trim().toLowerCase();
  return items.filter(
    (item) =>
      (quizId == null || item.source_quiz_id === quizId) &&
      (!term || item.question_text.toLowerCase().includes(term)),
  );
}

/*
 * What the class's question bank pop-up will download, so the button, the
 * sentence describing it and the file name always agree. It downloads the
 * ticked questions among the ones shown.
 *   className  this class's name
 *   quiz       the chosen quiz ({ title }), or null for every quiz
 *   search     the search box
 *   shown      how many questions the list shows
 *   ticked     how many of those are ticked
 *   loading    still loading the class's questions
 *   empty      the class has no questions in the bank
 */
export function exportPlan({ className, quiz = null, search = "", shown, ticked, loading = false, empty = false }) {
  const filename = quiz
    ? `${fileSlug(quiz.title) || "quiz"}-questions.csv`
    : `${fileSlug(className) || "class"}-question-bank.csv`;
  const idle = (summary) => ({ disabled: true, button: "Download", summary, filename });

  if (loading) return { disabled: true, button: "Loading…", summary: "Loading this class's questions…", filename };
  if (empty) return idle("This class has no questions in the bank yet.");
  if (!shown) return idle("No questions match.");
  if (!ticked) return idle("Tick the questions to download.");

  const from = quiz ? `the quiz “${quiz.title}”` : className;
  const term = search.trim();
  const which = ticked === shown
    ? (ticked === 1 ? "1 question" : `All ${ticked} questions`)
    : `${ticked} of ${shown} questions`;
  return {
    disabled: false,
    button: `Download ${plural(ticked, "question")}`,
    summary: `${which} from ${from}${term ? ` matching “${term}”` : ""}.`,
    filename,
  };
}
