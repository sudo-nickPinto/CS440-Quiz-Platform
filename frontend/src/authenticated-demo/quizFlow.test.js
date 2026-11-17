import { describe, expect, it, vi } from "vitest";

import {
  findPendingSubmission,
  pendingSubmissionFor,
  quizFlowState,
  sendQuizForApproval,
  showsQuizFlow,
} from "./quizFlow";

const ME = 7;

function quiz(overrides = {}) {
  return {
    quiz_id: 10,
    class_id: 4,
    author_id: ME,
    status: "DRAFT",
    can_edit: true,
    hosting: { can_host: false, reason: "not_published", message: "x" },
    ...overrides,
  };
}

describe("showsQuizFlow", () => {
  it("shows for owners and organizers", () => {
    expect(showsQuizFlow(quiz())).toBe(true);
    expect(showsQuizFlow(quiz({ hosting: { can_host: true } }))).toBe(true);
  });

  it("hides when the server hides the approval state", () => {
    for (const reason of ["not_host", "not_in_class", "class_archived", "quiz_archived"]) {
      expect(showsQuizFlow(quiz({ hosting: { can_host: false, reason } }))).toBe(false);
    }
  });

  it("hides for archived quizzes, quizzes with no class, or no hosting info", () => {
    expect(showsQuizFlow(quiz({ status: "ARCHIVED" }))).toBe(false);
    expect(showsQuizFlow(quiz({ class_id: null }))).toBe(false);
    expect(showsQuizFlow(quiz({ hosting: undefined }))).toBe(false);
    expect(showsQuizFlow(null)).toBe(false);
  });
});

describe("pendingSubmissionFor", () => {
  it("picks the newest pending request for this quiz", () => {
    const items = [
      { submission_id: 1, quiz_id: 10, status: "PENDING", submitted_at: "2026-11-01" },
      { submission_id: 2, quiz_id: 10, status: "PENDING", submitted_at: "2026-11-05" },
      { submission_id: 3, quiz_id: 11, status: "PENDING", submitted_at: "2026-11-09" },
      { submission_id: 4, quiz_id: 10, status: "REJECTED", submitted_at: "2026-11-10" },
    ];
    expect(pendingSubmissionFor(items, 10).submission_id).toBe(2);
    expect(pendingSubmissionFor(items, 12)).toBeNull();
    expect(pendingSubmissionFor(undefined, 10)).toBeNull();
  });
});

describe("quizFlowState", () => {
  it("a hostable quiz is ready to host", () => {
    const state = quizFlowState({
      quiz: quiz({ status: "PUBLISHED", hosting: { can_host: true } }),
      accountId: ME,
      pending: null,
    });
    expect(state).toMatchObject({ step: 3, label: "Approved", action: "host" });
  });

  it("your own pending request can be withdrawn", () => {
    const state = quizFlowState({
      quiz: quiz({ status: "PUBLISHED", hosting: { can_host: false, reason: "pending_approval" } }),
      accountId: ME,
      pending: { submission_id: 50, submitted_by_id: ME },
    });
    expect(state).toMatchObject({
      step: 2,
      label: "Waiting for approval",
      action: "withdraw",
    });
  });

  it("someone else's pending request is reviewed by the organizer", () => {
    const state = quizFlowState({
      quiz: quiz({ author_id: 2, status: "PUBLISHED" }),
      accountId: ME,
      pending: { submission_id: 50, submitted_by_id: 2, submitter_name: "Amy" },
    });
    expect(state).toMatchObject({ step: 2, action: "review" });
    expect(state.note).toContain("Amy");
  });

  it("edits made after sending are called out", () => {
    const state = quizFlowState({
      quiz: quiz({ status: "DRAFT" }),
      accountId: ME,
      pending: { submission_id: 50, submitted_by_id: ME },
    });
    expect(state.note).toContain("newer edits");
  });

  it("the owner can send a draft", () => {
    const state = quizFlowState({ quiz: quiz(), accountId: ME, pending: null });
    expect(state).toMatchObject({ step: 1, label: "Draft", action: "send" });
  });

  it("explains a rejection", () => {
    const state = quizFlowState({
      quiz: quiz({ status: "PUBLISHED", hosting: { can_host: false, reason: "rejected" } }),
      accountId: ME,
      pending: null,
    });
    expect(state.action).toBe("send");
    expect(state.note).toContain("rejected");
  });

  it("only the owner can send unpublished edits", () => {
    const draft = quizFlowState({
      quiz: quiz({ author_id: 2, status: "DRAFT" }),
      accountId: ME,
      pending: null,
    });
    expect(draft.action).toBeNull();

    const published = quizFlowState({
      quiz: quiz({ author_id: 2, status: "PUBLISHED" }),
      accountId: ME,
      pending: null,
    });
    expect(published.action).toBe("send");
  });

  it("returns null when the track is hidden", () => {
    expect(
      quizFlowState({
        quiz: quiz({ hosting: { can_host: false, reason: "not_host" } }),
        accountId: ME,
        pending: null,
      }),
    ).toBeNull();
  });
});

describe("sendQuizForApproval", () => {
  function fakeApi(current, { conflict = false } = {}) {
    return vi.fn(async (path, options = {}) => {
      if (path === "/quizzes/10") return current;
      if (path.endsWith("/publish")) {
        return { version: { quiz_version_id: 200 } };
      }
      if (path === "/classes/4/quiz-submissions") {
        if (conflict) {
          const error = new Error("Already sent");
          error.code = "quiz_submission_conflict";
          throw error;
        }
        return { submission_id: 50, body: JSON.parse(options.body) };
      }
      throw new Error(`unexpected ${path}`);
    });
  }

  it("publishes a draft, then submits the new version", async () => {
    const api = fakeApi({ status: "DRAFT", revision: 3, version: { quiz_version_id: 199 } });

    const result = await sendQuizForApproval(api, 4, 10);

    expect(result.body).toEqual({ quiz_version_id: 200 });
    const publish = api.mock.calls.find(([path]) => path.endsWith("/publish"));
    expect(publish[0]).toBe("/classes/4/quizzes/10/publish");
    expect(JSON.parse(publish[1].body)).toEqual({ expected_revision: 3 });
  });

  it("submits an already-published version without publishing again", async () => {
    const api = fakeApi({ status: "PUBLISHED", revision: 3, version: { quiz_version_id: 150 } });

    const result = await sendQuizForApproval(api, 4, 10);

    expect(result.body).toEqual({ quiz_version_id: 150 });
    expect(api.mock.calls.some(([path]) => path.endsWith("/publish"))).toBe(false);
  });

  it("treats a version that's already waiting or approved as sent", async () => {
    const api = fakeApi(
      { status: "PUBLISHED", revision: 3, version: { quiz_version_id: 150 } },
      { conflict: true },
    );

    await expect(sendQuizForApproval(api, 4, 10)).resolves.toBeNull();
  });

  it("passes other errors on", async () => {
    const api = vi.fn(async () => {
      throw Object.assign(new Error("Nope"), { code: "quiz_edit_denied" });
    });

    await expect(sendQuizForApproval(api, 4, 10)).rejects.toThrow("Nope");
  });
});

describe("findPendingSubmission", () => {
  // A class with `total` pending requests, newest first, 100 per page.
  // `target` is the position (0 = newest) of quiz 10's request, if any.
  function pagedApi(total, target) {
    const items = Array.from({ length: total }, (_, index) => ({
      submission_id: 1000 + index,
      quiz_id: index === target ? 10 : 500 + index,
      status: "PENDING",
      submitted_by_id: 7,
      submitted_at: `2026-11-11T12:00:${String(59 - (index % 60)).padStart(2, "0")}Z`,
    }));
    const totalPages = Math.ceil(total / 100);
    return vi.fn(async (path) => {
      const page = Number(new URL(path, "http://test").searchParams.get("page"));
      return {
        items: items.slice((page - 1) * 100, page * 100),
        pagination: { page, page_size: 100, total_items: total, total_pages: totalPages },
      };
    });
  }

  it("finds a request beyond the first 100 pending submissions", async () => {
    const api = pagedApi(250, 180);

    const found = await findPendingSubmission(api, 4, 10);

    expect(found.submission_id).toBe(1180);
    expect(api).toHaveBeenCalledTimes(2);
    expect(api.mock.calls[0][0]).toContain("status=PENDING");
    expect(api.mock.calls[0][0]).toContain("page_size=100");
  });

  it("stops at the first page that has the quiz", async () => {
    const api = pagedApi(250, 3);

    await findPendingSubmission(api, 4, 10);

    expect(api).toHaveBeenCalledTimes(1);
  });

  it("reads every page before deciding there's no request", async () => {
    const api = pagedApi(250, null);

    await expect(findPendingSubmission(api, 4, 10)).resolves.toBeNull();
    expect(api).toHaveBeenCalledTimes(3);
  });

  it("handles an empty list in one request", async () => {
    const api = vi.fn(async () => ({
      items: [],
      pagination: { page: 1, page_size: 100, total_items: 0, total_pages: 0 },
    }));

    await expect(findPendingSubmission(api, 4, 10)).resolves.toBeNull();
    expect(api).toHaveBeenCalledTimes(1);
  });

  it("fails loudly on an unreadable response instead of guessing", async () => {
    const api = vi.fn(async () => ({ nope: true }));

    await expect(findPendingSubmission(api, 4, 10)).rejects.toThrow(
      "approval status could not be read",
    );
  });

  it("passes the abort signal through", async () => {
    const api = pagedApi(1, 0);
    const controller = new AbortController();

    await findPendingSubmission(api, 4, 10, { signal: controller.signal });

    expect(api.mock.calls[0][1]).toEqual({ signal: controller.signal });
  });
});
