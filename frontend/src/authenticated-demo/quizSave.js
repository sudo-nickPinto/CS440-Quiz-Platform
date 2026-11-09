// Saving from the quiz editor, kept free of React so it can be tested.

// Classes a new quiz can be written in: ones the caller is an active member
// of and that aren't archived.
export function quizClassChoices(classes) {
  return classes.filter(
    (item) => item.membershipStatus === "ACTIVE" && !item.archived,
  );
}

// Saves the draft (PUT for an existing quiz, POST for a new one) and, when
// `publish` is set, publishes it. Publishing doesn't make it hostable: the
// version still needs class approval before anyone can host it.
//
// The draft is saved either way. If publishing fails the saved draft is
// returned with publishFailed, so the caller opens it (where Publish quiz can
// retry) rather than leaving the form up, where saving again would duplicate
// a new quiz.
export async function saveQuiz(
  api,
  { payload, existingQuiz = null, classId = null, publish = false },
) {
  const editing = existingQuiz !== null;
  const body = editing
    ? { ...payload, expected_revision: existingQuiz.revision }
    : payload;
  const path = editing
    ? `/classes/${existingQuiz.class_id}/quizzes/${existingQuiz.quiz_id}`
    : `/classes/${classId}/quizzes`;

  const saved = await api(path, {
    method: editing ? "PUT" : "POST",
    body: JSON.stringify(body),
  });

  if (!publish) return { quiz: saved, publishFailed: false };

  try {
    const published = await api(
      `/classes/${saved.class_id}/quizzes/${saved.quiz_id}/publish`,
      {
        method: "POST",
        body: JSON.stringify({ expected_revision: saved.revision }),
      },
    );
    return { quiz: published, publishFailed: false };
  } catch {
    return { quiz: saved, publishFailed: true };
  }
}
