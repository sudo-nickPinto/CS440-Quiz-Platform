import { expect, test } from "@playwright/test";

import { IDS, openClass } from "./workflow-fixture";

// 45 accounts, "Person 01" … "Person 45", served a page at a time like
// GET /classes/{id}/student-suggestions.
const PEOPLE = Array.from({ length: 45 }, (_, index) => {
  const n = String(index + 1).padStart(2, "0");
  return {
    account_id: 100 + index,
    email: `person${n}.with.a.rather.long.address@students.gettysburg.edu`,
    display_name: `Person ${n}`,
    membership_status: null,
  };
});

async function suggestionRoutes(page, { slowSearch } = {}) {
  const asked = [];
  await page.route("**/__test_api/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace(/^.*__test_api/, "");
    if (path !== `/classes/${IDS.CLASS_ID}/student-suggestions`) return route.fallback();
    const q = (url.searchParams.get("q") ?? "").toLowerCase();
    const limit = Number(url.searchParams.get("limit"));
    const offset = Number(url.searchParams.get("offset"));
    asked.push({ q, limit, offset });
    if (q && slowSearch) await new Promise((resolve) => setTimeout(resolve, slowSearch));
    const matches = PEOPLE.filter(
      (person) => !q || person.display_name.toLowerCase().startsWith(q),
    );
    return route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(matches.slice(offset, offset + limit)),
    });
  });
  return asked;
}

async function openAddStudent(page, options) {
  await openClass(page, { as: "organizer", path: `/app/classes/${IDS.CLASS_ID}?view=admin` });
  const asked = await suggestionRoutes(page, options);
  await page.reload();
  await page.getByRole("button", { name: "+ Add student" }).click();
  const dialog = page.getByRole("dialog", { name: /^Add to/ });
  return { dialog, asked, options: dialog.getByRole("option") };
}

test("Add student lists people on open and loads more as you scroll", async ({ page }) => {
  const { dialog, asked, options } = await openAddStudent(page);

  // Without typing anything, the first page is listed.
  await expect(options).toHaveCount(20);
  await expect(options.first()).toContainText("Person 01");
  expect(asked[0]).toEqual({ q: "", limit: 20, offset: 0 });

  // About four rows fit before scrolling.
  const box = dialog.locator(".cl-suggest-box");
  const rows = await box.evaluate((element) => {
    const row = element.querySelector("li").getBoundingClientRect().height;
    return element.clientHeight / row;
  });
  expect(rows).toBeGreaterThan(3.5);
  expect(rows).toBeLessThan(5.5);

  // Scrolling to the bottom loads the next pages until everyone is there.
  for (const expected of [40, 45]) {
    await box.evaluate((element) => element.scrollTo(0, element.scrollHeight));
    await expect(options).toHaveCount(expected);
  }
  await expect(options.last()).toContainText("Person 45");
  await expect(dialog.getByText("Loading more…")).toHaveCount(0);
});

test("typing filters the list without blanking it", async ({ page }) => {
  const { dialog, options } = await openAddStudent(page, { slowSearch: 800 });
  await expect(options).toHaveCount(20);

  await dialog.getByPlaceholder("Search by name or email…").fill("person 1");
  // While the slower search is on its way, the previous results stay.
  await page.waitForTimeout(400);
  await expect(options).toHaveCount(20);
  // Then the filtered list replaces them.
  await expect(options).toHaveCount(10);
  await expect(options.first()).toContainText("Person 10");
});

test("long emails stay on one line on a phone", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const { dialog, options } = await openAddStudent(page);
  await expect(options).toHaveCount(20);
  const email = dialog.locator(".cl-pmail").first();
  const fit = await email.evaluate((element) => ({
    oneLine: element.getClientRects().length === 1,
    cut: element.scrollWidth > element.clientWidth,
    ellipsis: getComputedStyle(element).textOverflow,
  }));
  expect(fit).toEqual({ oneLine: true, cut: true, ellipsis: "ellipsis" });
});
