import { describe, expect, it } from "vitest";

import { matchesTyped, trashRows, trashSelection } from "./trashHelpers";

const TRASH = {
  classes: [
    { class_id: 4, name: "CS 440", semester: "Fall 2026", days_left: 30 },
  ],
  quizzes: [
    {
      quiz_id: 9,
      title: "Week 3",
      class_name: "CS 440",
      class_in_trash: true,
      days_left: 1,
    },
  ],
  sessions: [
    {
      session_id: 31,
      quiz_title: "Week 3",
      class_name: "CS 216",
      class_in_trash: false,
      days_left: 12,
    },
  ],
};

describe("matchesTyped", () => {
  it("ignores case and extra spaces", () => {
    expect(matchesTyped("  cs   440 ", "CS 440")).toBe(true);
    expect(matchesTyped("CS 44", "CS 440")).toBe(false);
    expect(matchesTyped("", "CS 440")).toBe(false);
  });
});

describe("trashRows", () => {
  it("lists classes, quizzes and sessions with a kind tag and days left", () => {
    const rows = trashRows(TRASH);
    expect(rows.map((row) => [row.key, row.kindLabel, row.days])).toEqual([
      ["class:4", "Class", "30 days left"],
      ["quiz:9", "Quiz", "Deleted tomorrow"],
      ["session:31", "Session", "12 days left"],
    ]);
    expect(rows[1].blocked).toBe(true);
    expect(rows[2].title).toBe("Week 3 · Session #31");
  });

  it("is empty before the trash loads", () => {
    expect(trashRows(null)).toEqual([]);
  });
});

describe("trashSelection", () => {
  it("groups the picked rows by kind", () => {
    expect(trashSelection(trashRows(TRASH))).toEqual({
      class_ids: [4],
      quiz_ids: [9],
      session_ids: [31],
    });
  });
});
