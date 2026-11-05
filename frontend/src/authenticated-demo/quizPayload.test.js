import { describe, expect, it } from "vitest";
import {
  normalizeEditorDefaultTime,
  questionPayloadChanged,
  quizQuestionToEditor,
  quizToEditor,
  toQuestionCreate,
  toQuizCreate,
} from "./quizPayload";

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

  it("reconstructs the saved quiz-wide timer instead of resetting to 20s", () => {
    const quiz = savedQuiz();
    const second = structuredClone(quiz.version.questions[0]);
    const third = structuredClone(quiz.version.questions[0]);
    second.question_id = 13;
    second.question_order = 2;
    third.question_id = 14;
    third.question_order = 3;
    third.time_limit_seconds = 45;
    quiz.version.questions.push(second, third);

    const editor = quizToEditor(quiz);

    expect(editor.defaultTime).toBe(600);
    expect(editor.questions.map((question) => question.limit)).toEqual([
      null,
      null,
      45,
    ]);
  });

  it("preserves question identity and revision for independent saves", () => {
    const question = savedQuiz().version.questions[0];
    question.revision = 4;

    const editorQuestion = quizQuestionToEditor(question);

    expect(editorQuestion.questionId).toBe(12);
    expect(editorQuestion.revision).toBe(4);
    expect(toQuestionCreate(editorQuestion, 0, 20).question_text).toBe(
      "Which answer?",
    );
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

  it("detects a changed inherited quiz-wide duration", () => {
    const editor = quizToEditor(savedQuiz());
    const question = editor.questions[0];

    expect(
      questionPayloadChanged(
        question,
        question,
        0,
        30,
        editor.defaultTime,
      ),
    ).toBe(true);
  });

  it("does not rewrite an explicit duration when the default changes", () => {
    const editor = quizToEditor(savedQuiz());
    const question = { ...editor.questions[0], limit: 45 };

    expect(
      questionPayloadChanged(question, question, 0, 30, 20),
    ).toBe(false);
  });

  it("reconstructs a remotely changed quiz-wide duration", () => {
    const editor = {
      defaultTime: 20,
      questions: [
        { id: "one", limit: 30 },
        { id: "two", limit: null },
        { id: "custom", limit: 45 },
      ],
    };

    const afterFirstUpdate = normalizeEditorDefaultTime(editor);
    expect(afterFirstUpdate.defaultTime).toBe(20);

    const afterSecondUpdate = normalizeEditorDefaultTime({
      ...afterFirstUpdate,
      questions: afterFirstUpdate.questions.map((question) =>
        question.id === "two" ? { ...question, limit: 30 } : question,
      ),
    });

    expect(afterSecondUpdate.defaultTime).toBe(30);
    expect(afterSecondUpdate.questions.map((question) => question.limit)).toEqual([
      null,
      null,
      45,
    ]);
  });

  it("keeps the existing quiz default while remote durations are tied", () => {
    const editor = normalizeEditorDefaultTime({
      defaultTime: 20,
      questions: [
        { id: "remote", limit: 30 },
        { id: "unchanged", limit: null },
      ],
    });

    expect(editor.defaultTime).toBe(20);
    expect(editor.questions.map((question) => question.limit)).toEqual([
      30,
      null,
    ]);
  });
});
