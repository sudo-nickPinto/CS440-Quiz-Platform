import { sendForApproval, submissionsPath } from "../classes/classHelpers";
import { useResource } from "./rest";

// The three steps every class quiz goes through before it can be hosted.
export const FLOW_STEPS = ["Draft", "Approval", "Ready to host"];

// Hosting reasons that come before the approval check on the server, so they
// say nothing about where the quiz stands (see backend/app/services/hosting.py).
const NO_FLOW_REASONS = new Set([
  "not_host",
  "not_in_class",
  "class_archived",
  "quiz_archived",
]);

// Whether the quiz page shows the Draft → Approval → Ready to host track.
// The owner and class organizers get it. Collaborators and other members
// get "not_host" from the server, which hides the approval state, so they
// keep the plain quiz page.
export function showsQuizFlow(quiz) {
  if (!quiz || quiz.status === "ARCHIVED" || !quiz.class_id) return false;
  const hosting = quiz.hosting;
  if (!hosting) return false;
  return hosting.can_host || !NO_FLOW_REASONS.has(hosting.reason);
}

// The newest pending submission for this quiz, from the class's submission
// list (organizers see every submission, members only their own).
export function pendingSubmissionFor(items, quizId) {
  if (!Array.isArray(items)) return null;
  return (
    items
      .filter((item) => item.quiz_id === quizId && item.status === "PENDING")
      .sort((a, b) =>
        String(b.submitted_at).localeCompare(String(a.submitted_at)),
      )[0] ?? null
  );
}

const DRAFT_NOTES = {
  rejected: "An organizer rejected the last version. Edit it, then send it again.",
  withdrawn: "The last request was withdrawn. Send it again when it's ready.",
  approval_outdated: "It changed since it was approved, so it needs approval again.",
  unpublished_changes: "It changed since it was approved, so it needs approval again.",
};

/**
 * Where the quiz stands and the one thing to do next.
 *
 * Returns null when the page shouldn't show the track (see showsQuizFlow).
 * Otherwise { step, label, action, note }:
 *   step    1 Draft, 2 Approval, 3 Ready to host
 *   label   "Draft" | "Waiting for approval" | "Approved"
 *   action  "send" | "withdraw" | "review" | "host" | null
 */
export function quizFlowState({ quiz, accountId, pending }) {
  if (!showsQuizFlow(quiz)) return null;

  if (quiz.hosting.can_host) {
    return {
      step: 3,
      label: "Approved",
      action: "host",
      note: "Approved for this class. Start a live session whenever you're ready.",
    };
  }

  if (pending) {
    const mine = pending.submitted_by_id === accountId;
    const edited = quiz.status === "DRAFT";
    return {
      step: 2,
      label: "Waiting for approval",
      // Members only ever see their own requests, so a pending request that
      // isn't yours means you're an organizer of the class.
      action: mine ? "withdraw" : "review",
      note: mine
        ? edited
          ? "Waiting for an organizer. Your newer edits aren't part of this request; send them once it's decided."
          : "Waiting for an organizer to approve it."
        : `${pending.submitter_name ?? "A member"} sent this for approval.`,
    };
  }

  const owner = quiz.author_id === accountId;
  // Sending a draft publishes it first, and only the owner can publish.
  // An already-published version can be sent by any editor.
  const canSend = owner || (quiz.can_edit && quiz.status === "PUBLISHED");
  return {
    step: 1,
    label: "Draft",
    action: canSend ? "send" : null,
    note: !canSend
      ? "Only the quiz owner can send these edits for approval."
      : DRAFT_NOTES[quiz.hosting.reason] ??
        "Send it to your class organizers. Once it's approved, you can host it.",
  };
}

// Publishes the latest edits if needed, then submits that version to the
// class. A version that's already waiting or approved counts as sent.
export async function sendQuizForApproval(api, classId, quizId) {
  const current = await api(`/quizzes/${quizId}`);
  try {
    return await sendForApproval(api, classId, {
      quiz_id: quizId,
      status: current.status,
      published_version_id:
        current.status === "PUBLISHED" ? current.version.quiz_version_id : null,
    });
  } catch (error) {
    if (error?.code === "quiz_submission_conflict") return null;
    throw error;
  }
}

// Where a quiz stands (Draft → Approval → Ready to host) for the people who
// can move it along. Reads the class's pending submissions, because the quiz
// itself doesn't say whether a request is waiting or who sent it.
export function useQuizFlow(quiz, accountId) {
  const visible = showsQuizFlow(quiz);
  const submissions = useResource(
    visible ? submissionsPath(quiz.class_id, 1, "newest", "PENDING", 100) : null,
  );
  const loading = visible && submissions.loading;
  const pending = loading
    ? null
    : pendingSubmissionFor(submissions.data?.items, quiz?.quiz_id);

  return {
    visible,
    loading,
    pending,
    state: visible && !loading ? quizFlowState({ quiz, accountId, pending }) : null,
    reload: submissions.reload,
  };
}
