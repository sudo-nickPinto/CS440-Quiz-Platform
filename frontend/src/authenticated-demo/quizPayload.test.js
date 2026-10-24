import { describe, expect, it } from "vitest";
import { quizToEditor, toQuizCreate } from "./quizPayload";

function savedQuiz() {
  return {
    version: {
      title: "Saved quiz",
      description: "Keep this description",
      questions: [
        {
          question_id: 12,
          question_order: 1,
          question_type: "MULTIPLE_CHOICE",
          question_text: "Which answer?",
          explanation: "Keep this explanation",
          time_limit_seconds: 600,
          base_points: 750,
          choices: [
            {
              choice_id: 22,
              choice_order: 2,
              choice_text: "Wrong",
              is_correct: false,
            },
            {
              choice_id: 21,
              choice_order: 1,
              choice_text: "Right",
              is_correct: true,
            },
          ],
        },
      ],
    },
  };
}

describe("editing saved quizzes", () => {
  it("preserves description, explanation, timing, points and choice order", () => {
    const payload = toQuizCreate(quizToEditor(savedQuiz()));

    expect(payload).toEqual({
      title: "Saved quiz",
      description: "Keep this description",
      questions: [
        {
          question_text: "Which answer?",
          explanation: "Keep this explanation",
          time_limit_seconds: 600,
          base_points: 750,
          choices: [
            { choice_text: "Right", is_correct: true },
            { choice_text: "Wrong", is_correct: false },
          ],
        },
      ],
    });
  });

  it("does not mutate the saved quiz when editor values change", () => {
    const quiz = savedQuiz();
    const editor = quizToEditor(quiz);

    editor.questions[0].options[0] = "Changed";
    editor.description = "Changed";

    expect(quiz.version.description).toBe("Keep this description");
    expect(
      quiz.version.questions[0].choices.find(
        (choice) => choice.choice_order === 1,
      ).choice_text,
    ).toBe("Right");
  });

  it("refuses multiple-correct-answer questions instead of losing answers", () => {
    const quiz = savedQuiz();

    quiz.version.questions[0].choices.forEach((choice) => {
      choice.is_correct = true;
    });

    expect(() => quizToEditor(quiz)).toThrow(
      "one correct answer",
    );
  });

  it("rejects invalid base points", () => {
    const editor = quizToEditor(savedQuiz());
    editor.questions[0].basePoints = 0;

    expect(() => toQuizCreate(editor)).toThrow("base points");
  });
});
