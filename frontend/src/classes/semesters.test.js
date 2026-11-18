import { describe, expect, it } from "vitest";

import {
  classLabel,
  nextSemester,
  semesterFor,
  semesterOptions,
} from "./semesters";

describe("semesterFor", () => {
  it("maps months to Spring, Summer and Fall", () => {
    expect(semesterFor(new Date(2027, 0, 15))).toBe("Spring 2027");
    expect(semesterFor(new Date(2027, 4, 31))).toBe("Spring 2027");
    expect(semesterFor(new Date(2027, 5, 1))).toBe("Summer 2027");
    expect(semesterFor(new Date(2026, 7, 20))).toBe("Fall 2026");
    expect(semesterFor(new Date(2026, 11, 31))).toBe("Fall 2026");
  });
});

describe("nextSemester", () => {
  it("goes from Fall to the next Spring and skips Summer", () => {
    expect(nextSemester("Fall 2026")).toBe("Spring 2027");
    expect(nextSemester("Spring 2027")).toBe("Fall 2027");
    expect(nextSemester("summer 2027")).toBe("Fall 2027");
  });

  it("counts from today when the label isn't a semester", () => {
    const today = new Date(2026, 10, 17);
    expect(nextSemester("Section B", today)).toBe("Spring 2027");
    expect(nextSemester(null, today)).toBe("Spring 2027");
  });
});

describe("semesterOptions", () => {
  it("suggests this semester and the next two", () => {
    expect(semesterOptions(new Date(2026, 10, 17))).toEqual([
      "Fall 2026",
      "Spring 2027",
      "Fall 2027",
    ]);
  });
});

describe("classLabel", () => {
  it("adds the semester when there is one", () => {
    expect(classLabel({ name: "CS 440", semester: "Fall 2026" })).toBe(
      "CS 440 · Fall 2026",
    );
    expect(classLabel({ name: "CS 440", semester: null })).toBe("CS 440");
  });
});
