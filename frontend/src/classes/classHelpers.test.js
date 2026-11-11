import { describe, expect, it } from "vitest";
import {
  approvalLabel,
  approvedQuizzesPath,
  canSubmitForApproval,
  myQuizzesPath,
  quizAccessLabel,
  quizStatusLabel,
  submissionPreviewPath,
  submissionsPath,
} from "./classHelpers";

describe("myQuizzesPath", () => {
  it("asks for the caller's own and shared quizzes, recently edited first", () => {
    expect(myQuizzesPath(4)).toBe(
      "/classes/4/quizzes?mine=true&page=1&page_size=25&sort=updated_at&order=desc",
    );
  });

  it("maps sort choices and pages", () => {
    expect(myQuizzesPath(4, 3, "title")).toBe(
      "/classes/4/quizzes?mine=true&page=3&page_size=25&sort=title&order=asc",
    );
    expect(myQuizzesPath(4, 1, "newest", 100)).toContain(
      "page_size=100&sort=created_at&order=desc",
    );
  });

  it("falls back to recently edited for an unknown sort", () => {
    expect(myQuizzesPath(4, 1, "bogus")).toContain("sort=updated_at");
  });
});

describe("labels", () => {
  it("names access and status", () => {
    expect(quizAccessLabel("OWNER")).toBe("Owner");
    expect(quizAccessLabel("EDITOR")).toBe("Editor");
    expect(quizAccessLabel(null)).toBe("—");
    expect(quizStatusLabel("PUBLISHED")).toBe("Published");
    expect(quizStatusLabel("weird")).toBe("—");
  });
});

describe("approval queue helpers", () => {
  it("builds the submitted-version preview path, or null for a bad address", () => {
    expect(submissionPreviewPath(4, 9)).toBe(
      "/classes/4/dashboard/submissions/9/preview",
    );
    expect(submissionPreviewPath("4", "x")).toBeNull();
    expect(submissionPreviewPath(undefined, 9)).toBeNull();
  });

  it("builds submission paths with a sort and an optional status", () => {
    expect(submissionsPath(4, 2, "oldest", "PENDING", 10)).toBe(
      "/classes/4/dashboard/submissions?page=2&page_size=10" +
        "&sort=submitted_at&order=asc&status=PENDING",
    );
    expect(submissionsPath(4, 1, "nope", "")).toBe(
      "/classes/4/dashboard/submissions?page=1&page_size=25" +
        "&sort=submitted_at&order=desc",
    );
    expect(submissionsPath(4, 1, "title", "BOGUS")).not.toContain("status=");
  });

  it("builds approved-quiz paths", () => {
    expect(approvedQuizzesPath(9, 1, "title")).toBe(
      "/classes/9/dashboard/approved-quizzes?page=1&page_size=24" +
        "&sort=title&order=asc",
    );
  });

  it("labels every approval state", () => {
    expect(approvalLabel(null)).toBe("Not submitted");
    expect(approvalLabel("PENDING")).toBe("Waiting for approval");
    expect(approvalLabel("APPROVED")).toBe("Approved");
  });

  it("only offers approval for a published version that isn't queued", () => {
    const quiz = {
      status: "PUBLISHED",
      my_access: "OWNER",
      published_version_id: 7,
      approval_status: null,
    };
    expect(canSubmitForApproval(quiz)).toBe(true);
    expect(canSubmitForApproval({ ...quiz, approval_status: "REJECTED" })).toBe(true);
    expect(canSubmitForApproval({ ...quiz, approval_status: "WITHDRAWN" })).toBe(true);
    expect(canSubmitForApproval({ ...quiz, approval_status: "PENDING" })).toBe(false);
    expect(canSubmitForApproval({ ...quiz, approval_status: "APPROVED" })).toBe(false);
    expect(canSubmitForApproval({ ...quiz, status: "DRAFT" })).toBe(false);
    expect(canSubmitForApproval({ ...quiz, my_access: null })).toBe(false);
    expect(canSubmitForApproval({ ...quiz, published_version_id: null })).toBe(false);
  });
});
