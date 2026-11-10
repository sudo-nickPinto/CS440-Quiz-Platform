import { describe, expect, it } from "vitest";
import { quizClassChoices, saveQuiz } from "./quizSave";

// A fake api() that records each call and answers from a list of responses
// (an Error in the list is thrown instead).
function fakeApi(...responses) {
  const calls = [];
  const api = async (path, options) => {
    calls.push({ path, method: options.method, body: JSON.parse(options.body) });
    const next = responses.shift();
    if (next instanceof Error) throw next;
    return next;
  };
  return { api, calls };
}

const draft = { quiz_id: 7, class_id: 3, revision: 4, status: "DRAFT" };
const published = { ...draft, revision: 5, status: "PUBLISHED" };

describe("quizClassChoices", () => {
  it("offers only active, unarchived classes", () => {
    const classes = [
      { id: 1, membershipStatus: "ACTIVE", archived: false },
      { id: 2, membershipStatus: "ACTIVE", archived: true },
      { id: 3, membershipStatus: "INVITED", archived: false },
      { id: 4, membershipStatus: "REMOVED", archived: false },
      { id: 5, membershipStatus: "ACTIVE", archived: false },
    ];
    expect(quizClassChoices(classes).map((item) => item.id)).toEqual([1, 5]);
  });

  it("is empty when the caller has no usable class", () => {
    expect(quizClassChoices([])).toEqual([]);
  });
});

describe("saveQuiz", () => {
  it("creates a new draft in the chosen class", async () => {
    const { api, calls } = fakeApi(draft);
    const result = await saveQuiz(api, { payload: { title: "Q" }, classId: 3 });

    expect(result).toEqual({ quiz: draft, publishFailed: false });
    expect(calls).toEqual([
      { path: "/classes/3/quizzes", method: "POST", body: { title: "Q" } },
    ]);
  });

  it("updates an existing quiz with its expected revision", async () => {
    const { api, calls } = fakeApi(draft);
    await saveQuiz(api, {
      payload: { title: "Q" },
      existingQuiz: { quiz_id: 7, class_id: 3, revision: 3 },
    });

    expect(calls).toEqual([
      {
        path: "/classes/3/quizzes/7",
        method: "PUT",
        body: { title: "Q", expected_revision: 3 },
      },
    ]);
  });

  it("saves then publishes with the saved revision", async () => {
    const { api, calls } = fakeApi(draft, published);
    const result = await saveQuiz(api, {
      payload: { title: "Q" },
      classId: 3,
      publish: true,
    });

    expect(result).toEqual({ quiz: published, publishFailed: false });
    expect(calls[1]).toEqual({
      path: "/classes/3/quizzes/7/publish",
      method: "POST",
      body: { expected_revision: 4 },
    });
  });

  it("returns the saved draft when publishing fails", async () => {
    const { api, calls } = fakeApi(draft, new Error("409"));
    const result = await saveQuiz(api, {
      payload: { title: "Q" },
      classId: 3,
      publish: true,
    });

    expect(result).toEqual({ quiz: draft, publishFailed: true });
    expect(calls).toHaveLength(2);
  });

  it("does not publish when saving fails", async () => {
    const { api, calls } = fakeApi(new Error("422"));
    await expect(
      saveQuiz(api, { payload: { title: "Q" }, classId: 3, publish: true }),
    ).rejects.toThrow("422");
    expect(calls).toHaveLength(1);
  });
});
