// Short labels for why a quiz can't be hosted yet. The backend also sends a
// full sentence (hosting.message), shown as the tooltip and screen-reader text.
export const HOSTING_LABELS = {
  not_in_class: "Not in a class",
  class_archived: "Class archived",
  not_host: "Owner or organizer only",
  quiz_archived: "Quiz archived",
  not_published: "Publish first",
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
