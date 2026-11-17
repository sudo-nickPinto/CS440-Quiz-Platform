import { describe, expect, it } from "vitest";

import { WHEEL_SPACING, wheelPosition, wheelTarget } from "./wheelMath";

describe("wheelPosition", () => {
  it("moves one question per spacing, later when dragged left", () => {
    expect(wheelPosition(2, -WHEEL_SPACING, 10)).toBe(3);
    expect(wheelPosition(2, WHEEL_SPACING * 2, 10)).toBe(0);
  });

  it("only overshoots the ends a little", () => {
    expect(wheelPosition(0, 500, 10)).toBe(-0.4);
    expect(wheelPosition(9, -500, 10)).toBe(9.4);
  });
});

describe("wheelTarget", () => {
  it("settles on the nearest question inside the quiz", () => {
    expect(wheelTarget(2.4, 10)).toBe(2);
    expect(wheelTarget(2.6, 10)).toBe(3);
    expect(wheelTarget(-0.4, 10)).toBe(0);
    expect(wheelTarget(9.4, 10)).toBe(9);
  });
});
