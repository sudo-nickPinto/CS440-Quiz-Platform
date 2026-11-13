import { describe, expect, it } from "vitest";

import { classesForNewQuiz } from "./newQuizClasses";

const classes = [
  { id: 1, name: "CS 216", membershipStatus: "ACTIVE", archived: false },
  { id: 2, name: "CS 111", membershipStatus: "ACTIVE", archived: true },
  { id: 3, name: "CS 440", membershipStatus: "INVITED", archived: false },
  { id: 4, name: "Biology", membershipStatus: "ACTIVE", archived: false },
];

describe("classesForNewQuiz", () => {
  it("keeps active, unarchived classes sorted by name", () => {
    expect(classesForNewQuiz(classes).map((item) => item.id)).toEqual([4, 1]);
  });

  it("handles a missing list", () => {
    expect(classesForNewQuiz(null)).toEqual([]);
  });
});
