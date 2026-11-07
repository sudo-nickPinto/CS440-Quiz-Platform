import { describe, expect, it } from "vitest";

import { canEditQuiz, quizEditorKey } from "./quizEditing";

describe("quiz editing availability", () => {
  it("lets an authorized editor reopen a saved draft", () => {
    expect(canEditQuiz({ can_edit: true, status: "DRAFT" })).toBe(true);
  });

  it("lets an authorized editor revise a published quiz", () => {
    expect(canEditQuiz({ can_edit: true, status: "PUBLISHED" })).toBe(true);
  });

  it("rejects archived quizzes and accounts without edit access", () => {
    expect(canEditQuiz({ can_edit: true, status: "ARCHIVED" })).toBe(false);
    expect(canEditQuiz({ can_edit: false, status: "DRAFT" })).toBe(false);
  });

  it("remounts the editor when the same draft receives a new revision", () => {
    const quiz = {
      quiz_id: 7,
      revision: 3,
      version: { quiz_version_id: 11 },
    };

    expect(quizEditorKey(quiz)).toBe("7:11:3");
    expect(quizEditorKey({ ...quiz, revision: 4 })).toBe("7:11:4");
  });
});
