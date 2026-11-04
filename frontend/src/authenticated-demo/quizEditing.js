export function canEditQuiz(quiz) {
  return (
    quiz.can_edit === true &&
    (quiz.status === "DRAFT" || quiz.status === "PUBLISHED")
  );
}
