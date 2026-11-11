// Short labels for why a quiz can't be hosted yet. The backend also sends a
// full sentence (hosting.message), shown as the tooltip and screen-reader text.
export const HOSTING_LABELS = {
  not_in_class: "Not in a class",
  class_archived: "Class archived",
  not_host: "Owner or organizer only",
  quiz_archived: "Quiz archived",
  not_published: "Publish first",
  unpublished_changes: "Publish changes first",
  not_submitted: "Needs approval",
  pending_approval: "Waiting for approval",
  rejected: "Approval rejected",
  withdrawn: "Approval withdrawn",
  approval_outdated: "New version needs approval",
};

// What the Host button should show for a quiz. Quiz responses carry
// `hosting` ({ can_host, reason, message }) from the same checks the
// start-session endpoint runs, so a blocked quiz never shows a live button.
export function hostingState(quiz, classId = quiz.class_id) {
  if (!classId) {
    return {
      canHost: false,
      label: HOSTING_LABELS.not_in_class,
      message: "This quiz isn't in a class, so it can't be hosted.",
    };
  }

  const hosting = quiz.hosting;
  // Older responses without `hosting`: let the server decide on click.
  if (!hosting || hosting.can_host) return { canHost: true };

  return {
    canHost: false,
    label: HOSTING_LABELS[hosting.reason] || "Can't host yet",
    message: hosting.message || "This quiz can't be hosted right now.",
  };
}

// Whether a page should show the Host control (a button, or the reason it
// can't be hosted yet) for this quiz. It shows for the quiz owner and class
// organizers, including on drafts, so "Publish first" can appear. Archived
// quizzes and people who could never host it (collaborators, members) see
// nothing.
export function showsHostControl(quiz, accountId) {
  if (quiz.status === "ARCHIVED") return false;
  if (quiz.hosting) {
    const { reason } = quiz.hosting;
    if (reason === "not_host") return false;
    // These are checked before "not_host", so they don't tell us whether
    // the caller could host. Only show them to the owner.
    if (reason === "class_archived" || reason === "not_in_class") {
      return quiz.author_id === accountId;
    }
    return true;
  }
  // Older responses without `hosting`: the previous rule.
  return quiz.status === "PUBLISHED" && quiz.author_id === accountId;
}
