// Classes where the caller can start a new quiz: active membership in a class
// that isn't archived (the same rule the class page uses for its "+" cell).
export function classesForNewQuiz(classes) {
  if (!Array.isArray(classes)) return [];
  return classes
    .filter((item) => item.membershipStatus === "ACTIVE" && !item.archived)
    .sort((a, b) => a.name.localeCompare(b.name));
}
