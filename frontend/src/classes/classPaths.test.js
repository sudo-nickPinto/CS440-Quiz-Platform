import { describe, expect, it } from "vitest";
import { classPagePath } from "./classPaths";

describe("classPagePath", () => {
  it("goes to the class, or the class list when there is none", () => {
    expect(classPagePath(4)).toBe("/app/classes/4");
    expect(classPagePath("7")).toBe("/app/classes/7");
    expect(classPagePath(null)).toBe("/app/classes");
    expect(classPagePath(undefined)).toBe("/app/classes");
    expect(classPagePath("x")).toBe("/app/classes");
  });
});
