export function fileSlug(text) {
  return (text ?? "").trim().toLowerCase()
    .replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

const plural = (count, word) => `${count} ${word}${count === 1 ? "" : "s"}`;

function courseNames(courses, classIds) {
  const names = courses.filter((course) => classIds.has(course.class_id)).map((course) => course.name);
  if (names.length === courses.length && names.length > 1) return "all your courses";
  if (names.length <= 2) return names.join(" and ");
  return `${names.length} courses`;
}

export function findQuiz(courses, quizId) {
  for (const course of courses) {
    const quiz = course.quizzes.find((item) => item.quiz_id === quizId);
    if (quiz) return { ...quiz, course };
  }
  return null;
}

/*
 * Works out what the admin question bank will download, so the request, the
 * button and the sentence describing it always agree.
 *   courses      GET /question-bank/sources courses
 *   classIds     Set of ticked course IDs
 *   quizId       chosen quiz, or null for every quiz
 *   search       the search box
 *   selectedIds  Set of ticked question IDs (wins over the filters)
 *   matching     how many questions the filters match
 */
export function exportPlan({ courses, classIds, quizId, search, selectedIds, matching }) {
  const class_ids = [...classIds].sort((a, b) => a - b);
  const quiz = quizId == null ? null : findQuiz(courses, quizId);
  const term = search.trim();

  if (selectedIds.size) {
    return {
      payload: { class_ids, bank_question_ids: [...selectedIds].sort((a, b) => a - b) },
      count: selectedIds.size,
      button: `Download ${plural(selectedIds.size, "selected question")}`,
      summary: `${plural(selectedIds.size, "selected question")}.`,
      filename: "selected-questions.csv",
    };
  }

  const payload = { class_ids };
  if (quiz) payload.quiz_id = quiz.quiz_id;
  if (term) payload.search = term;

  const from = quiz ? `the quiz “${quiz.title}”` : courseNames(courses, classIds);
  const matchingText = term ? ` matching “${term}”` : "";
  const single = courses.filter((course) => classIds.has(course.class_id));
  const filename = quiz
    ? `${fileSlug(quiz.title) || "quiz"}-questions.csv`
    : single.length === 1
      ? `${fileSlug(single[0].name) || "course"}-question-bank.csv`
      : "question-bank.csv";

  return {
    payload,
    count: matching,
    button: term || quiz ? `Download ${plural(matching, "question")}` : `Download all ${plural(matching, "question")}`,
    summary: class_ids.length
      ? `${matching === 1 ? "1 question" : `All ${matching} questions`} from ${from}${matchingText}.`
      : "Choose at least one course.",
    filename,
  };
}
