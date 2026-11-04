import { describe, expect, it } from "vitest";
import {
  myQuizzesPath,
  quizAccessLabel,
  quizStatusLabel,
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
