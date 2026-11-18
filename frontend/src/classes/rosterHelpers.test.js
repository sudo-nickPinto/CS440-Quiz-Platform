import { describe, expect, it } from "vitest";

import {
  outcomeLabel,
  rosterContentType,
  rosterHasChanges,
  rosterName,
  rosterSummary,
  suggestionQuery,
  suggestionStatus,
} from "./rosterHelpers";

describe("rosterSummary", () => {
  it("lists non-zero outcomes in a fixed order", () => {
    expect(
      rosterSummary({ skipped: 1, added: 3, expected: 2, already_in_class: 0 }),
    ).toBe("3 added · 2 no account yet · 1 skipped");
  });

  it("is empty for no counts", () => {
    expect(rosterSummary(undefined)).toBe("");
  });
});

describe("rosterHasChanges", () => {
  it("is true only when an import would do something", () => {
    expect(rosterHasChanges({ already_in_class: 4, skipped: 1 })).toBe(false);
    expect(rosterHasChanges({ expected: 1 })).toBe(true);
  });
});

describe("rosterName and outcomeLabel", () => {
  it("shows the registrar's Last, First order", () => {
    expect(rosterName({ first_name: "Lin Mei", last_name: "Chen" })).toBe(
      "Chen, Lin Mei",
    );
    expect(rosterName({ first_name: null, last_name: null })).toBe("—");
  });

  it("labels known outcomes and passes unknown ones through", () => {
    expect(outcomeLabel("expected")).toBe("No account yet");
    expect(outcomeLabel("something_new")).toBe("something_new");
  });
});

describe("suggestions", () => {
  it("waits for two characters and tidies spaces", () => {
    expect(suggestionQuery(" a ")).toBe("");
    expect(suggestionQuery("  maya   riv ")).toBe("maya riv");
  });

  it("only offers Add to people not already in the class", () => {
    expect(suggestionStatus("ACTIVE").canAdd).toBe(false);
    expect(suggestionStatus("INVITED").canAdd).toBe(true);
    expect(suggestionStatus("REQUESTED").label).toBe("Waiting for approval");
    expect(suggestionStatus(null)).toEqual({ label: null, canAdd: true });
  });
});

describe("rosterContentType", () => {
  it("sends Excel files with the Excel type and everything else as CSV", () => {
    expect(rosterContentType({ name: "CS 440A F26.XLSX" })).toMatch(/spreadsheetml/);
    expect(rosterContentType({ name: "roster.csv" })).toBe("text/csv");
  });
});
