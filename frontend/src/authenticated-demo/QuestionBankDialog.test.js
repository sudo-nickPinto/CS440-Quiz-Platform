import { describe, expect, it } from "vitest";

import { toEditorQuestion } from "./questionBankModel";


describe("question-bank editor conversion", () => {
  it("creates an independent editor question from a saved bank snapshot", () => {
    const bankItem = {
      question_text: "Which value is even?",
      explanation: null,
      choices: [
        { choice_text: "2", is_correct: true },
        { choice_text: "3", is_correct: false },
      ],
    };

    const converted = toEditorQuestion(bankItem);

    expect(converted).toMatchObject({
      text: "Which value is even?",
      explanation: "",
      options: ["2", "3"],
      correct: 0,
      limit: null,
      basePoints: 1000,
    });
    expect(converted.id).toEqual(expect.any(String));
    expect(converted.options).not.toBe(bankItem.choices);
  });

  it("rejects multi-correct content instead of silently dropping correct answers", () => {
    expect(() => toEditorQuestion({
      question_text: "Select both prime numbers",
      explanation: "",
      choices: [
        { choice_text: "2", is_correct: true },
        { choice_text: "3", is_correct: true },
        { choice_text: "4", is_correct: false },
      ],
    })).toThrow("exactly one correct answer");
  });
});
