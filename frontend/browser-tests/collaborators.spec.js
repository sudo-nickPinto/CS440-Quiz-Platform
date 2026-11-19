import { expect, test } from "@playwright/test";

import { IDS, openClass } from "./workflow-fixture";

// The member in the workflow fixture owns quiz 10 in the test class.
const QUIZ = `/classes/${IDS.CLASS_ID}/quizzes/10`;
const MAYA = {
  account_id: 41,
  email: "riverma01@gettysburg.edu",
  display_name: "Maya Rivera",
};

// Collaborator routes with real state: adding and removing change both the
// editors list and what the search says.
async function collaboratorRoutes(page) {
  const state = { editors: new Set(), adds: 0, removes: 0, searches: 0 };
  await page.route("**/__test_api/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace(/^.*__test_api/, "");
    const method = route.request().method();
    const json = (body, status = 200) =>
      route.fulfill({
        status,
        contentType: "application/json",
        body: JSON.stringify(body),
      });

    if (path === `${QUIZ}/collaborator-suggestions` && method === "GET") {
      state.searches += 1;
      return json([
        { ...MAYA, is_collaborator: state.editors.has(MAYA.account_id) },
      ]);
    }
    if (path === `${QUIZ}/collaborators` && method === "GET") {
      return json(
        [...state.editors].map(() => ({
          ...MAYA,
          quiz_id: 10,
          permission: "EDITOR",
          shared_by_id: 2,
          created_at: "2026-11-18T00:00:00Z",
        })),
      );
    }
    if (path === `${QUIZ}/collaborators` && method === "POST") {
      state.adds += 1;
      state.editors.add(MAYA.account_id);
      return json(
        {
          ...MAYA,
          quiz_id: 10,
          permission: "EDITOR",
          shared_by_id: 2,
          created_at: "2026-11-18T00:00:00Z",
        },
        201,
      );
    }
    if (path === `${QUIZ}/collaborators/${MAYA.account_id}` && method === "DELETE") {
      state.removes += 1;
      state.editors.delete(MAYA.account_id);
      return route.fulfill({ status: 204 });
    }
    return route.fallback();
  });
  return state;
}

test("a collaborator can be added, removed and added again from the search", async ({
  page,
}) => {
  await openClass(page, { as: "member", path: "/app/quizzes/10" });
  const state = await collaboratorRoutes(page);
  await page.reload();

  await page.getByRole("button", { name: "Add collaborator" }).first().click();
  // By name: the remove confirmation is a second dialog.
  const dialog = page.getByRole("dialog", { name: "Who else can edit this quiz?" });
  await dialog
    .getByPlaceholder("Search this class by name or email…")
    .fill("riv");

  const results = dialog.getByRole("listbox", { name: "People in this class" });
  const maya = results.getByRole("option", { name: /Maya Rivera/ });
  const addMaya = maya.getByRole("button", { name: "Add", exact: true });
  await expect(addMaya).toBeVisible();
  // Searches made for the typing alone.
  const typedSearches = state.searches;

  // Add: the result turns into "Editor" and Maya is in the editors list.
  await addMaya.click();
  await expect(maya.getByText("Editor", { exact: true })).toBeVisible();
  await expect(addMaya).toHaveCount(0);
  const removeMaya = dialog.getByRole("button", { name: "Remove", exact: true });
  await expect(removeMaya).toBeVisible();

  // Remove: the result goes back to "Add" right away, not a stale "Editor".
  await removeMaya.click();
  await page.getByRole("button", { name: "Remove access" }).click();
  await expect(addMaya).toBeVisible();
  await expect(maya.getByText("Editor", { exact: true })).toHaveCount(0);
  await expect(removeMaya).toHaveCount(0);

  // Re-add works.
  await addMaya.click();
  await expect(maya.getByText("Editor", { exact: true })).toBeVisible();
  await expect(dialog.getByText("2 added")).toBeVisible();

  expect(state.adds).toBe(2);
  expect(state.removes).toBe(1);
  // The search is asked again after changes, not only when typing. Quick
  // changes in a row can share one refresh (the search waits for a pause),
  // so this checks for a refresh rather than one per change.
  await expect.poll(() => state.searches).toBeGreaterThan(typedSearches);
  await expect(maya.getByText("Editor", { exact: true })).toBeVisible();
});
