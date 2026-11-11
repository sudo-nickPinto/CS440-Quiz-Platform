import { describe, expect, it } from "vitest";

import {
  classesForNewQuiz,
  draftsInProgress,
  questionCountLabel,
} from "./draftHelpers";

const classes = [
  { id: 1, name: "CS 216", membershipStatus: "ACTIVE", archived: false },
  { id: 2, name: "CS 111", membershipStatus: "ACTIVE", archived: true },
  { id: 3, name: "CS 440", membershipStatus: "INVITED", archived: false },
  { id: 4, name: "Biology", membershipStatus: "ACTIVE", archived: false },
];

function quiz(overrides) {
  return {
    quiz_id: 10,
    class_id: 1,
    author_id: 7,
    status: "DRAFT",
    title: "Recursion check",
    question_count: 3,
    created_at: "2026-11-09T12:00:00Z",
    ...overrides,
  };
}

describe("classesForNewQuiz", () => {
  it("keeps active, unarchived classes sorted by name", () => {
    expect(classesForNewQuiz(classes).map((item) => item.id)).toEqual([4, 1]);
  });

  it("handles a missing list", () => {
    expect(classesForNewQuiz(null)).toEqual([]);
  });
});

describe("draftsInProgress", () => {
  it("lists owned and shared drafts with their class", () => {
    const drafts = draftsInProgress(
      [
        quiz({ quiz_id: 10, author_id: 7 }),
        quiz({ quiz_id: 11, author_id: 8, created_at: "2026-11-10T12:00:00Z" }),
      ],
      classes,
      7,
    );

    expect(drafts.map((item) => [item.quizId, item.owned])).toEqual([
      [11, false],
      [10, true],
    ]);
    expect(drafts[0].className).toBe("CS 216");
    expect(drafts[0].classId).toBe(1);
  });

  it("leaves out published and archived quizzes", () => {
    const drafts = draftsInProgress(
      [
        quiz({ quiz_id: 10, status: "PUBLISHED" }),
        quiz({ quiz_id: 11, status: "ARCHIVED" }),
        quiz({ quiz_id: 12 }),
      ],
      classes,
      7,
    );

    expect(drafts.map((item) => item.quizId)).toEqual([12]);
  });

  it("drops drafts whose class the caller can no longer open", () => {
    const drafts = draftsInProgress(
      [
        quiz({ quiz_id: 10, class_id: 99 }),
        quiz({ quiz_id: 11, class_id: null }),
      ],
      classes,
      7,
    );

    expect(drafts).toEqual([]);
  });

  it("marks drafts in archived classes and names untitled drafts", () => {
    const [draft] = draftsInProgress(
      [quiz({ class_id: 2, title: "  " })],
      classes,
      7,
    );

    expect(draft.classArchived).toBe(true);
    expect(draft.title).toBe("Untitled quiz");
  });
});

describe("questionCountLabel", () => {
  it("pluralizes", () => {
    expect(questionCountLabel(1)).toBe("1 question");
    expect(questionCountLabel(0)).toBe("0 questions");
    expect(questionCountLabel(4)).toBe("4 questions");
  });
});
