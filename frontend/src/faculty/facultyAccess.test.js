import { describe, expect, it } from "vitest";

import {
  grantedLabel,
  historySentence,
  isFaculty,
  looksLikeEmail,
  orderFaculty,
} from "./facultyAccess";

describe("isFaculty", () => {
  it("is true only for active ADMIN accounts", () => {
    expect(isFaculty({ role: "ADMIN", is_active: true })).toBe(true);
    expect(isFaculty({ role: "USER", is_active: true })).toBe(false);
    expect(isFaculty({ role: "ADMIN", is_active: false })).toBe(false);
    expect(isFaculty(null)).toBe(false);
  });
});

describe("looksLikeEmail", () => {
  it("accepts ordinary addresses with surrounding spaces", () => {
    expect(looksLikeEmail("alopez@gettysburg.edu")).toBe(true);
    expect(looksLikeEmail("  alopez@gettysburg.edu  ")).toBe(true);
  });

  it("rejects obvious typos", () => {
    for (const value of ["", "alopez", "alopez@", "@gettysburg.edu", "a b@c.d", "a@b"]) {
      expect(looksLikeEmail(value)).toBe(false);
    }
  });
});

describe("grantedLabel", () => {
  it("names who added someone", () => {
    const label = grantedLabel({
      granted_at: "2026-11-13T15:02:11Z",
      granted_by_name: "Jane Kim",
    });
    expect(label.startsWith("Added by Jane Kim · ")).toBe(true);
  });

  it("explains faculty set up before this page existed", () => {
    expect(grantedLabel({ granted_at: null, granted_by_name: null })).toBe(
      "Set up by a maintainer",
    );
  });
});

describe("historySentence", () => {
  it("describes grants and removals", () => {
    const base = { actor_name: "Jane Kim", account_name: "Ana Lopez" };
    expect(historySentence({ ...base, action: "GRANTED" })).toBe(
      "Jane Kim gave faculty access to Ana Lopez",
    );
    expect(historySentence({ ...base, action: "REVOKED" })).toBe(
      "Jane Kim removed faculty access from Ana Lopez",
    );
  });
});

describe("orderFaculty", () => {
  it("puts me first and keeps the rest in server order", () => {
    const people = [
      { account_id: 1, is_me: false },
      { account_id: 2, is_me: true },
      { account_id: 3, is_me: false },
    ];
    expect(orderFaculty(people).map((p) => p.account_id)).toEqual([2, 1, 3]);
    expect(orderFaculty(undefined)).toEqual([]);
  });
});
