import { describe, expect, it } from "vitest";

import {
  classLabel,
  compareSemesters,
  groupCourses,
  newSemesterChoices,
  nextSemester,
  previousSemester,
  semesterChoices,
  semesterFor,
} from "./semesters";

const NOV_2026 = new Date(2026, 10, 17);

describe("semesterFor", () => {
  it("maps months to Spring, Summer and Fall", () => {
    expect(semesterFor(new Date(2027, 0, 15))).toBe("Spring 2027");
    expect(semesterFor(new Date(2027, 4, 31))).toBe("Spring 2027");
    expect(semesterFor(new Date(2027, 5, 1))).toBe("Summer 2027");
    expect(semesterFor(new Date(2026, 7, 20))).toBe("Fall 2026");
    expect(semesterFor(new Date(2026, 11, 31))).toBe("Fall 2026");
  });
});

describe("nextSemester and previousSemester", () => {
  it("step between regular semesters and skip Summer", () => {
    expect(nextSemester("Fall 2026")).toBe("Spring 2027");
    expect(nextSemester("Spring 2027")).toBe("Fall 2027");
    expect(nextSemester("summer 2027")).toBe("Fall 2027");
    expect(previousSemester("Spring 2027")).toBe("Fall 2026");
    expect(previousSemester("Fall 2026")).toBe("Spring 2026");
    expect(previousSemester("Summer 2026")).toBe("Spring 2026");
  });

  it("count from today when the label isn't a semester", () => {
    expect(nextSemester("Section B", NOV_2026)).toBe("Spring 2027");
    expect(nextSemester(null, NOV_2026)).toBe("Spring 2027");
  });
});

describe("compareSemesters", () => {
  it("puts semesters in time order", () => {
    const sorted = ["Fall 2027", "Spring 2027", "Summer 2027", "Fall 2026"].sort(
      compareSemesters,
    );
    expect(sorted).toEqual(["Fall 2026", "Spring 2027", "Summer 2027", "Fall 2027"]);
  });
});

describe("semesterChoices", () => {
  it("offers one semester before today and three after", () => {
    expect(semesterChoices({ today: NOV_2026 })).toEqual([
      "Spring 2026",
      "Fall 2026",
      "Spring 2027",
      "Fall 2027",
      "Spring 2028",
    ]);
  });
});

describe("newSemesterChoices", () => {
  it("starts after the newest semester and skips ones the course has", () => {
    expect(newSemesterChoices(["Fall 2026", "Fall 2027"], NOV_2026)).toEqual([
      "Spring 2028",
      "Fall 2028",
      "Spring 2029",
      "Fall 2029",
    ]);
    expect(newSemesterChoices(["Fall 2026", "Spring 2027"], NOV_2026)[0]).toBe(
      "Fall 2027",
    );
  });

  it("starts from today when the course has no semester yet", () => {
    expect(newSemesterChoices([], NOV_2026)[0]).toBe("Fall 2026");
  });
});

describe("groupCourses", () => {
  const course = (id, semester, extra = {}) => ({
    id,
    name: "CS 440",
    semester,
    parentClassId: id === 1 ? null : 1,
    canManage: true,
    archived: false,
    ...extra,
  });

  it("shows one card per course you organize, on its newest active semester", () => {
    const cards = groupCourses([
      course(1, "Fall 2026"),
      course(2, "Spring 2027"),
      course(3, "Fall 2027", { archived: true }),
    ]);
    expect(cards).toHaveLength(1);
    expect(cards[0]).toMatchObject({ id: 2, semesterCount: 3 });
  });

  it("shows the newest one when every semester is archived", () => {
    const cards = groupCourses([
      course(1, "Fall 2026", { archived: true }),
      course(2, "Spring 2027", { archived: true }),
    ]);
    expect(cards[0].id).toBe(2);
  });

  it("keeps a card per class for students", () => {
    const cards = groupCourses([
      course(1, "Fall 2026", { canManage: false }),
      course(2, "Spring 2027", { canManage: false }),
    ]);
    expect(cards.map((card) => card.id)).toEqual([1, 2]);
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
