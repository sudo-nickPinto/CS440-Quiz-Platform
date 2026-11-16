import { describe, expect, it } from "vitest";

import { toEditorQuestion } from "./questionBankModel";


describe("question-bank editor conversion", () => {
  it("creates an independent editor question from a saved bank snapshot", () => {
    const bankItem = {
      question_text: "Which value is even?",
      explanation: null,
      time_limit_seconds: 30,
      base_points: 750,
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
      limit: 30,
      basePoints: 750,
    });
    expect(converted.id).toEqual(expect.any(String));
    expect(converted.options).not.toBe(bankItem.choices);
  });
});
