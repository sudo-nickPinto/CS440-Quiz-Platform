import { describe, expect, it } from "vitest";

import { quizQuestionsToCsv, toEditorQuestion, unsupportedReason } from "./questionBankModel";


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

  it("flags multi-correct questions as unsupported so they can't be selected", () => {
    const multi = { choices: [{ is_correct: true }, { is_correct: true }] };
    const single = { choices: [{ is_correct: false }, { is_correct: true }] };
    expect(unsupportedReason(multi)).toMatch("exactly one correct answer");
    expect(unsupportedReason(single)).toBeNull();
  });
});

describe("quiz CSV export", () => {
  const choice = (choice_order, choice_text, is_correct = false) => ({ choice_order, choice_text, is_correct });

  it("writes saved questions in order, in the import template format", () => {
    const csv = quizQuestionsToCsv([
      { question_order: 2, question_text: "Both primes", explanation: null,
        choices: [choice(2, "4"), choice(1, "2", true), choice(3, "3", true)] },
      { question_order: 1, question_text: 'Pick, "two"', explanation: "",
        choices: [choice(1, "1"), choice(2, "2", true), choice(3, "=3")] },
    ]);

    expect(csv).toBe(
      "question_text,explanation,choice_a,choice_b,choice_c,choice_d,correct_choices\r\n"
      + '"Pick, ""two""",,1,2,\'=3,,B\r\n'
      + "Both primes,,2,4,3,,A|C\r\n",
    );
  });

  it("refuses questions with more choices than the template holds", () => {
    expect(() => quizQuestionsToCsv([
      { question_order: 1, question_text: "Five", explanation: null,
        choices: [1, 2, 3, 4, 5].map((n) => choice(n, String(n), n === 1)) },
    ])).toThrow("at most 4 choices");
  });
});
