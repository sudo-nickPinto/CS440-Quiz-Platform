import { describe, expect, it } from "vitest";

import {
  ANSWER_LIMIT,
  ANSWER_SOFT_LIMIT,
  QUESTION_LIMIT,
  QUESTION_SOFT_LIMIT,
  charCount,
} from "./model";

describe("text limits", () => {
  it("allows 200-character questions and 120-character answers", () => {
    expect(QUESTION_LIMIT).toBe(200);
    expect(ANSWER_LIMIT).toBe(120);
    expect(QUESTION_SOFT_LIMIT).toBe(120);
    expect(ANSWER_SOFT_LIMIT).toBe(60);
  });
});

describe("charCount", () => {
  it("stays hidden up to the soft limit", () => {
    expect(charCount(0, 200, 120).visible).toBe(false);
    expect(charCount(120, 200, 120).visible).toBe(false);
  });

  it("shows as long between the soft and hard limits", () => {
    expect(charCount(121, 200, 120)).toEqual({
      visible: true,
      long: true,
      over: false,
      label: "121/200",
    });
    expect(charCount(200, 200, 120).long).toBe(true);
  });

  it("flags older text that is already past the hard limit", () => {
    expect(charCount(150, 120, 60)).toEqual({
      visible: true,
      long: false,
      over: true,
      label: "150/120",
    });
  });
});
