import { describe, expect, it, vi } from "vitest";

import {
  canApplyRemoteQuestion,
  nextAggregateRevision,
  remoteStructureDecision,
  saveAggregateQuiz,
  saveDraftQuestions,
} from "./quizDraftSave";

function question(id, questionId, text) {
  return {
    id,
    questionId,
    revision: 1,
    text,
    explanation: "",
    options: ["Yes", "No"],
    correct: 0,
    limit: null,
    basePoints: 1000,
  };
}

function response(questionId, text, quizRevision) {
  return {
    quiz_revision: quizRevision,
    question: {
      question_id: questionId,
      question_order: questionId,
      question_type: "MULTIPLE_CHOICE",
      question_text: text,
      explanation: null,
      time_limit_seconds: 20,
      base_points: 1000,
      revision: 1,
      choices: [
        {
          choice_id: questionId * 10,
          choice_order: 1,
          choice_text: "Yes",
          is_correct: true,
        },
        {
          choice_id: questionId * 10 + 1,
          choice_order: 2,
          choice_text: "No",
          is_correct: false,
        },
      ],
    },
  };
}

describe("collaborative draft saves", () => {
  it("keeps aggregate saves stale after an ignored question update and unrelated event", async () => {
    const baseline = question("saved-1", 1, "Original");
    const locallyEdited = question("saved-1", 1, "Local edit");

    const aggregateStale = !canApplyRemoteQuestion(locallyEdited, baseline);
    const revisionAfterUnrelatedEvent = nextAggregateRevision(
      4,
      5,
      aggregateStale,
    );

    expect(aggregateStale).toBe(true);
    expect(revisionAfterUnrelatedEvent).toBe(4);

    const api = vi.fn().mockResolvedValue({ quiz_id: 9 });
    await saveAggregateQuiz({
      editor: {
        title: "Locally renamed quiz",
        description: "",
        defaultTime: 20,
        questions: [locallyEdited],
      },
      revision: revisionAfterUnrelatedEvent,
      existingQuiz: { class_id: 3, quiz_id: 9 },
      api,
    });

    expect(JSON.parse(api.mock.calls[0][1].body).expected_revision).toBe(4);
  });

  it("keeps the loaded revision after a remote structural update when local content is dirty", async () => {
    const baselineEditor = {
      title: "Quiz",
      description: "",
      defaultTime: 20,
      questions: [question("saved-1", 1, "Original")],
    };
    const editor = {
      ...baselineEditor,
      questions: [question("saved-1", 1, "Local edit")],
    };

    const decision = remoteStructureDecision({
      editor,
      baselineEditor,
      currentRevision: 4,
      incomingRevision: 5,
    });

    expect(decision).toEqual({ reload: false, revision: 4 });
    const api = vi.fn().mockResolvedValue({ quiz_id: 9 });
    await saveAggregateQuiz({
      editor,
      revision: decision.revision,
      existingQuiz: { class_id: 3, quiz_id: 9 },
      api,
    });

    expect(JSON.parse(api.mock.calls[0][1].body).expected_revision).toBe(4);
  });

  it("does not post an already-created question again after a partial save retry", async () => {
    const saved = question("saved-1", 1, "Saved question");
    let progress = {
      editor: {
        title: "Quiz",
        description: "",
        defaultTime: 20,
        questions: [
          saved,
          question("new-a", null, "First new question"),
          question("new-b", null, "Second new question"),
        ],
      },
      baselineEditor: {
        title: "Quiz",
        description: "",
        defaultTime: 20,
        questions: [saved],
      },
    };
    const existingQuiz = { class_id: 3, quiz_id: 9 };
    const api = vi
      .fn()
      .mockResolvedValueOnce(response(2, "First new question", 2))
      .mockRejectedValueOnce(new Error("temporary failure"))
      .mockResolvedValueOnce(response(3, "Second new question", 3));

    await expect(
      saveDraftQuestions({
        ...progress,
        existingQuiz,
        api,
        onProgress: (next) => {
          progress = next;
        },
      }),
    ).rejects.toThrow("temporary failure");

    expect(progress.editor.questions[1].questionId).toBe(2);
    expect(progress.baselineEditor.questions).toHaveLength(2);

    await saveDraftQuestions({
      ...progress,
      existingQuiz,
      api,
      onProgress: (next) => {
        progress = next;
      },
    });

    const postedBodies = api.mock.calls.map(([, options]) =>
      JSON.parse(options.body).question_text,
    );
    expect(postedBodies).toEqual([
      "First new question",
      "Second new question",
      "Second new question",
    ]);
    expect(progress.editor.questions.map((item) => item.questionId)).toEqual([
      1,
      2,
      3,
    ]);
  });
});
