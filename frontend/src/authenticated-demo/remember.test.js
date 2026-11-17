import { describe, expect, it } from "vitest";
import { pickStart, readRemembered, writeRemembered } from "./remember";

describe("pickStart", () => {
  it("prefers an explicit value, then a valid saved one, then the default", () => {
    expect(pickStart("Approvals", "Students", { override: "Presentations" })).toBe("Presentations");
    expect(pickStart("Approvals", "Students")).toBe("Approvals");
    expect(pickStart(undefined, "Students")).toBe("Students");
    expect(pickStart(undefined, () => 1)).toBe(1);
  });

  it("drops saved values that are no longer valid", () => {
    const isValid = (value) => ["Present", "Participate"].includes(value);
    expect(pickStart("My quizzes", "Present", { isValid })).toBe("Present");
    expect(pickStart("Participate", "Present", { isValid, override: null })).toBe("Participate");
  });
});

describe("remembered storage", () => {
  it("is a no-op without a key or without storage", () => {
    writeRemembered(null, 3);
    expect(readRemembered(null)).toBeUndefined();
    // The unit tests run without a browser; reads fall back to undefined.
    expect(readRemembered("missing")).toBeUndefined();
  });
});
