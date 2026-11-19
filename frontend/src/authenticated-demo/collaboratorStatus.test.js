import { describe, expect, it } from "vitest";

import { isEditorNow, withEditorChange } from "./collaboratorStatus";

const maya = { account_id: 41, is_collaborator: false };

describe("isEditorNow", () => {
  it("uses the search result when nothing changed in the pop-up", () => {
    expect(isEditorNow(maya, {})).toBe(false);
    expect(isEditorNow({ ...maya, is_collaborator: true }, undefined)).toBe(true);
  });

  it("follows add → remove → re-add even while the result is stale", () => {
    let changes = {};
    changes = withEditorChange(changes, 41, true);
    expect(isEditorNow(maya, changes)).toBe(true);

    // Removed: the old result still says is_collaborator, but they can be
    // added again right away.
    changes = withEditorChange(changes, 41, false);
    expect(isEditorNow({ ...maya, is_collaborator: true }, changes)).toBe(false);

    changes = withEditorChange(changes, 41, true);
    expect(isEditorNow(maya, changes)).toBe(true);
  });

  it("only changes the account it names", () => {
    const changes = withEditorChange({}, 41, true);
    expect(isEditorNow({ account_id: 42, is_collaborator: false }, changes)).toBe(false);
  });
});
