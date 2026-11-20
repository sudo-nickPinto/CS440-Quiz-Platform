import { describe, expect, it } from "vitest";

import { exportPlan, visibleQuestions } from "./questionBankExport";

const item = (id, quizId, text) => ({ bank_question_id: id, source_quiz_id: quizId, question_text: text });
const items = [item(1, 10, "Git branch?"), item(2, 10, "Git fetch?"), item(3, 20, "Scrum sprint?")];
const base = { className: "CS 440", shown: 8, ticked: 8 };

describe("class question bank: what's shown", () => {
  it("narrows to one quiz and to a search anywhere in the question", () => {
    expect(visibleQuestions(items).map((q) => q.bank_question_id)).toEqual([1, 2, 3]);
    expect(visibleQuestions(items, { quizId: 10 }).map((q) => q.bank_question_id)).toEqual([1, 2]);
    expect(visibleQuestions(items, { search: " FETCH " }).map((q) => q.bank_question_id)).toEqual([2]);
    expect(visibleQuestions(items, { quizId: 20, search: "git" })).toEqual([]);
  });
});

describe("class question bank: what will download", () => {
  it("downloads every ticked question of the class by default", () => {
    expect(exportPlan(base)).toEqual({
      disabled: false,
      button: "Download 8 questions",
      summary: "All 8 questions from CS 440.",
      filename: "cs-440-question-bank.csv",
    });
  });

  it("says when only some of the shown questions are ticked", () => {
    expect(exportPlan({ ...base, ticked: 3 }).summary).toBe("3 of 8 questions from CS 440.");
  });

  it("names the quiz and the search", () => {
    const plan = exportPlan({ ...base, quiz: { title: "Git Basics" }, search: " git ", shown: 1, ticked: 1 });
    expect(plan.button).toBe("Download 1 question");
    expect(plan.summary).toBe("1 question from the quiz “Git Basics” matching “git”.");
    expect(plan.filename).toBe("git-basics-questions.csv");
  });

  it("never shows a count of 0 on the button", () => {
    expect(exportPlan({ ...base, loading: true })).toMatchObject({ disabled: true, button: "Loading…" });
    expect(exportPlan({ ...base, empty: true })).toMatchObject({
      disabled: true, button: "Download", summary: "This class has no questions in the bank yet.",
    });
    expect(exportPlan({ ...base, shown: 0, ticked: 0 })).toMatchObject({
      disabled: true, button: "Download", summary: "No questions match.",
    });
    expect(exportPlan({ ...base, ticked: 0 })).toMatchObject({
      disabled: true, button: "Download", summary: "Tick the questions to download.",
    });
  });
});
