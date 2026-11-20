import { describe, expect, it } from "vitest";

import { editorQuestionsToCsv, toEditorQuestion, unsupportedReason } from "./questionBankModel";


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
  it("serializes the editor's questions in the import template format", () => {
    const csv = editorQuestionsToCsv([
      { text: "Pick, \"two\"", explanation: "", options: ["1", "2", "=3"], correct: 1 },
    ]);

    expect(csv).toBe(
      "question_text,explanation,choice_a,choice_b,choice_c,choice_d,correct_choices\r\n"
      + "\"Pick, \"\"two\"\"\",,1,2,'=3,,B\r\n",
    );
  });
});
