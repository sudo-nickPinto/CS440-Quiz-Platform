import { describe, expect, it } from "vitest";

import { charCount, TEXT_LIMIT } from "./model";

describe("charCount", () => {
  it("limits question and answer text to 120 characters", () => {
    expect(TEXT_LIMIT).toBe(120);
  });

  it("stays hidden until the text nears the limit", () => {
    expect(charCount(0).visible).toBe(false);
    expect(charCount(99).visible).toBe(false);
    expect(charCount(100)).toEqual({ visible: true, over: false, label: "100/120" });
    expect(charCount(120)).toEqual({ visible: true, over: false, label: "120/120" });
  });

  it("flags older text that is already past the limit", () => {
    expect(charCount(150)).toEqual({ visible: true, over: true, label: "150/120" });
  });
});
