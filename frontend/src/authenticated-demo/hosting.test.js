import { describe, expect, it } from "vitest";

import { HOSTING_LABELS, hostingState } from "./hosting";

describe("hostingState", () => {
  it("allows hosting when the server says the quiz can be hosted", () => {
    const quiz = { quiz_id: 1, class_id: 4, hosting: { can_host: true } };
    expect(hostingState(quiz)).toEqual({ canHost: true });
  });

  it("leaves the decision to the server for responses without hosting", () => {
    expect(hostingState({ quiz_id: 1, class_id: 4 })).toEqual({ canHost: true });
  });

  it("shows a short label and the server's sentence when blocked", () => {
    const quiz = {
      quiz_id: 1,
      class_id: 4,
      hosting: {
        can_host: false,
        reason: "pending_approval",
        message: "This quiz is waiting for a class organizer to approve it.",
      },
    };
    expect(hostingState(quiz)).toEqual({
      canHost: false,
      label: "Waiting for approval",
      message: "This quiz is waiting for a class organizer to approve it.",
    });
  });

  it("has a label for every reason the backend sends", () => {
    for (const reason of [
      "not_in_class",
      "class_archived",
      "not_host",
      "quiz_archived",
      "not_published",
      "not_submitted",
      "pending_approval",
      "rejected",
      "withdrawn",
      "approval_outdated",
    ]) {
      expect(HOSTING_LABELS[reason]).toBeTruthy();
    }
  });

  it("falls back to a generic label for an unknown reason", () => {
    const state = hostingState({
      class_id: 4,
      hosting: { can_host: false, reason: "something_new", message: null },
    });
    expect(state.canHost).toBe(false);
    expect(state.label).toBe("Can't host yet");
    expect(state.message).toBeTruthy();
  });

  it("blocks quizzes that are not in a class", () => {
    expect(hostingState({ quiz_id: 1, class_id: null }).canHost).toBe(false);
  });

  it("uses a class id passed in for lists that don't include one", () => {
    expect(hostingState({ quiz_id: 1 }, 7)).toEqual({ canHost: true });
  });
});
