import { describe, expect, it } from "vitest";

import {
  ANSWER_LIMIT,
  COUNT_WARN,
  EXPLANATION_LIMIT,
  QUESTION_LIMIT,
  charCount,
} from "./model";

describe("text limits", () => {
  it("allows 200-character questions, 120-character answers and 1000-character explanations", () => {
    expect(QUESTION_LIMIT).toBe(200);
    expect(ANSWER_LIMIT).toBe(120);
    expect(EXPLANATION_LIMIT).toBe(1000);
    expect(COUNT_WARN).toBe(20);
  });
});

describe("charCount", () => {
  it("stays hidden until 20 characters before the limit", () => {
    expect(charCount(0, 200).visible).toBe(false);
    expect(charCount(179, 200).visible).toBe(false);
  });

  it("shows the count from 20 characters before the limit", () => {
    expect(charCount(180, 200)).toEqual({ visible: true, label: "180/200" });
    expect(charCount(100, 120).visible).toBe(true);
    expect(charCount(980, 1000).label).toBe("980/1,000");
  });

  it("still shows older text that is over the limit", () => {
    expect(charCount(150, 120)).toEqual({ visible: true, label: "150/120" });
  });
});
