import { describe, expect, it } from "vitest";

import { canEditQuiz } from "./quizEditing";

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
});
