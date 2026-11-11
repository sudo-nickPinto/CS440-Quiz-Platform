import { describe, expect, it } from "vitest";

import {
  canHostApprovedQuiz,
  canSubmitQuiz,
  paginate,
  submissionMatchesQuiz,
} from "./quizWorkflow";

const publishedQuiz = {
  quiz_id: 10,
  class_id: 4,
  author_id: 7,
  status: "PUBLISHED",
  can_edit: true,
  version: {
    quiz_version_id: 100,
    published_at: "2026-11-10T12:00:00Z",
  },
};

const activeClass = {
  id: 4,
  archived: false,
  membershipStatus: "ACTIVE",
  canManage: false,
};

describe("submission eligibility", () => {
  it("allows an authorized editor to submit a published version", () => {
    expect(canSubmitQuiz(publishedQuiz)).toBe(true);
  });

  it("does not allow read-only users to submit", () => {
    expect(canSubmitQuiz({ ...publishedQuiz, can_edit: false })).toBe(false);
  });

  it("does not allow drafts or archived quizzes", () => {
    expect(
      canSubmitQuiz({
        ...publishedQuiz,
        status: "DRAFT",
        version: {
          ...publishedQuiz.version,
          published_at: null,
        },
      }),
    ).toBe(false);

    expect(canSubmitQuiz({ ...publishedQuiz, status: "ARCHIVED" })).toBe(false);
  });

  it("matches submission status to the exact class and version", () => {
    expect(
      submissionMatchesQuiz(
        { class_id: 4, quiz_version_id: 100 },
        publishedQuiz,
      ),
    ).toBe(true);

    expect(
      submissionMatchesQuiz(
        { class_id: 4, quiz_version_id: 99 },
        publishedQuiz,
      ),
    ).toBe(false);

    expect(
      submissionMatchesQuiz(
        { class_id: 5, quiz_version_id: 100 },
        publishedQuiz,
      ),
    ).toBe(false);
  });
});

describe("approved hosting controls", () => {
  const approved = { author_id: 7 };

  it("allows the owner and a class organizer", () => {
    expect(canHostApprovedQuiz(approved, 7, activeClass)).toBe(true);

    expect(
      canHostApprovedQuiz(approved, 8, {
        ...activeClass,
        canManage: true,
      }),
    ).toBe(true);
  });

  it("does not grant hosting merely because someone is a member", () => {
    expect(canHostApprovedQuiz(approved, 8, activeClass)).toBe(false);
  });

  it("blocks archived classes and inactive membership", () => {
    expect(
      canHostApprovedQuiz(approved, 7, {
        ...activeClass,
        archived: true,
      }),
    ).toBe(false);

    expect(
      canHostApprovedQuiz(approved, 7, {
        ...activeClass,
        membershipStatus: "REMOVED",
      }),
    ).toBe(false);
  });
});

describe("list pagination", () => {
  it("clamps the page when filtering reduces the results", () => {
    const result = paginate([1, 2, 3], 5, 2);

    expect(result.page).toBe(2);
    expect(result.totalPages).toBe(2);
    expect(result.items).toEqual([3]);
  });

  it("handles an empty list", () => {
    expect(paginate([], 3)).toEqual({
      page: 1,
      totalPages: 1,
      items: [],
    });
  });
});
