import { describe, expect, it } from "vitest";

import { canEditQuiz } from "./quizEditing";

describe("quiz editing availability", () => {
  it("lets the owner reopen a saved draft", () => {
    expect(canEditQuiz({ author_id: 7, status: "DRAFT" }, 7)).toBe(true);
  });

  it("lets the owner revise a published quiz", () => {
    expect(canEditQuiz({ author_id: 7, status: "PUBLISHED" }, 7)).toBe(true);
  });

  it("rejects archived quizzes and non-owners", () => {
    expect(canEditQuiz({ author_id: 7, status: "ARCHIVED" }, 7)).toBe(false);
    expect(canEditQuiz({ author_id: 7, status: "DRAFT" }, 8)).toBe(false);
  });
});
