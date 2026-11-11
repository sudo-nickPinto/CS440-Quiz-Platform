// Draft discovery helpers for the Classes page and the "new quiz" picker.
// GET /quizzes returns every quiz the caller owns or collaborates on, in the
// classes where they are an active member. These helpers turn that list into
// the "Drafts in progress" cards without another request per class.

// Classes where the caller can start a new quiz: active membership in a class
// that isn't archived (the same rule the class page uses for its "+" cell).
export function classesForNewQuiz(classes) {
  if (!Array.isArray(classes)) return [];
  return classes
    .filter((item) => item.membershipStatus === "ACTIVE" && !item.archived)
    .sort((a, b) => a.name.localeCompare(b.name));
}

// Unpublished work the caller can reopen. A quiz edited after publishing is a
// DRAFT again, so it shows here too. The class page calls the same quizzes
// "Draft", so the label matches everywhere.
export function draftsInProgress(quizzes, classes, accountId) {
  if (!Array.isArray(quizzes)) return [];

  const classById = new Map(
    (Array.isArray(classes) ? classes : []).map((item) => [item.id, item]),
  );

  return quizzes
    .filter((quiz) => quiz.status === "DRAFT" && classById.has(quiz.class_id))
    .map((quiz) => {
      const owningClass = classById.get(quiz.class_id);
      return {
        quizId: quiz.quiz_id,
        title: quiz.title?.trim() || "Untitled quiz",
        questionCount: Number(quiz.question_count) || 0,
        classId: owningClass.id,
        className: owningClass.name,
        classArchived: owningClass.archived,
        owned: quiz.author_id === accountId,
        createdAt: quiz.created_at,
      };
    })
    .sort(
      (a, b) =>
        String(b.createdAt).localeCompare(String(a.createdAt)) ||
        b.quizId - a.quizId,
    );
}

export function questionCountLabel(count) {
  return `${count} ${count === 1 ? "question" : "questions"}`;
}
