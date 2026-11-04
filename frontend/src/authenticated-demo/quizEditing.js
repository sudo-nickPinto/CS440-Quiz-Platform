export function canEditQuiz(quiz, accountId) {
  return (
    quiz.author_id === accountId &&
    (quiz.status === "DRAFT" || quiz.status === "PUBLISHED")
  );
}
