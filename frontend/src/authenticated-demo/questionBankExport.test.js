import { describe, expect, it } from "vitest";

import { exportPlan } from "./questionBankExport";

const courses = [
  { class_id: 1, name: "CS 440", archived: false, question_count: 5,
    quizzes: [{ quiz_id: 10, title: "Git Basics", question_count: 3 }] },
  { class_id: 2, name: "BIO 101", archived: false, question_count: 2, quizzes: [] },
];
const base = { courses, quizId: null, search: "", selectedIds: new Set(), matching: 7 };

describe("admin question bank export plan", () => {
  it("downloads everything in all courses", () => {
    const plan = exportPlan({ ...base, classIds: new Set([2, 1]) });
    expect(plan.payload).toEqual({ class_ids: [1, 2] });
    expect(plan.button).toBe("Download all 7 questions");
    expect(plan.summary).toBe("All 7 questions from all your courses.");
    expect(plan.filename).toBe("question-bank.csv");
  });

  it("names a single course and its file", () => {
    const plan = exportPlan({ ...base, classIds: new Set([1]), matching: 5 });
    expect(plan.summary).toBe("All 5 questions from CS 440.");
    expect(plan.filename).toBe("cs-440-question-bank.csv");
  });

  it("downloads one quiz, narrowed by search", () => {
    const plan = exportPlan({ ...base, classIds: new Set([1]), quizId: 10, search: " git ", matching: 1 });
    expect(plan.payload).toEqual({ class_ids: [1], quiz_id: 10, search: "git" });
    expect(plan.button).toBe("Download 1 question");
    expect(plan.summary).toBe("1 question from the quiz “Git Basics” matching “git”.");
    expect(plan.filename).toBe("git-basics-questions.csv");
  });

  it("ticked questions win over the filters", () => {
    const plan = exportPlan({
      ...base, classIds: new Set([1]), quizId: 10, search: "git", selectedIds: new Set([9, 3]),
    });
    expect(plan.payload).toEqual({ class_ids: [1], bank_question_ids: [3, 9] });
    expect(plan.count).toBe(2);
    expect(plan.button).toBe("Download 2 selected questions");
    expect(plan.summary).toBe("2 selected questions.");
  });

  it("asks for a course when none is ticked", () => {
    expect(exportPlan({ ...base, classIds: new Set(), matching: 0 }).summary)
      .toBe("Choose at least one course.");
  });
});
