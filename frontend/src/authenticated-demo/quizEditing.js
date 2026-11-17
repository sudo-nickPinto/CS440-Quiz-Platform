export function canEditQuiz(quiz) {
  return (
    quiz.can_edit === true &&
    (quiz.status === "DRAFT" || quiz.status === "PUBLISHED")
  );
}

export function quizEditorKey(quiz) {
  return `${quiz.quiz_id}:${quiz.version.quiz_version_id}:${quiz.revision}`;
}
