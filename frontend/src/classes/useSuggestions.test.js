import { describe, expect, it } from "vitest";

import { mergeSuggestionPage } from "./useSuggestions";

const person = (id) => ({ account_id: id, display_name: `P${id}` });
const empty = { key: null, items: [], hasMore: false };

describe("suggestion pages", () => {
  it("replaces the list with a new search's first page", () => {
    const shown = { key: "a", items: [person(1), person(2)], hasMore: true };
    expect(mergeSuggestionPage(shown, { key: "b", offset: 0, limit: 2, items: [person(3)] }))
      .toEqual({ key: "b", items: [person(3)], hasMore: false });
  });

  it("adds later pages and knows a short page is the last", () => {
    const first = mergeSuggestionPage(empty, { key: "a", offset: 0, limit: 2, items: [person(1), person(2)] });
    expect(first.hasMore).toBe(true);
    const second = mergeSuggestionPage(first, { key: "a", offset: 2, limit: 2, items: [person(2), person(3)] });
    expect(second.items.map((item) => item.account_id)).toEqual([1, 2, 3]);
    const last = mergeSuggestionPage(second, { key: "a", offset: 4, limit: 2, items: [person(4)] });
    expect(last).toEqual({ key: "a", items: [1, 2, 3, 4].map(person), hasMore: false });
  });

  it("ignores a later page that belongs to an older search", () => {
    const shown = { key: "b", items: [person(9)], hasMore: true };
    expect(mergeSuggestionPage(shown, { key: "a", offset: 20, limit: 20, items: [person(1)] }))
      .toBe(shown);
  });
});
