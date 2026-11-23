import { expect, test } from "@playwright/test";

import { IDS, openClass } from "./workflow-fixture";

const { CLASS_ID, SUBMISSION_ID, SUBMITTED_VERSION_ID } = IDS;
const SUBMISSIONS = `/classes/${CLASS_ID}/quiz-submissions`;
const DECISION = `${SUBMISSIONS}/${SUBMISSION_ID}`;
const PREVIEW = `/app/classes/${CLASS_ID}/submissions/${SUBMISSION_ID}`;

function button(page, name) {
  return page.getByRole("button", { name, exact: true });
}

async function noHorizontalScroll(page) {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > window.innerWidth + 1,
  );
  expect(overflow).toBe(false);
}

test("member sends a quiz for approval, withdraws it, and sends it again", async ({
  page,
}) => {
  const state = await openClass(page, { as: "member" });

  await button(page, "Send for approval").click();
  await expect(button(page, "Withdraw request")).toBeVisible();
  expect(state.calls).toContainEqual({
    method: "POST",
    path: SUBMISSIONS,
    body: { quiz_version_id: SUBMITTED_VERSION_ID },
  });

  await button(page, "Withdraw request").click();
  await expect(button(page, "Send for approval")).toBeVisible();
  expect(state.calls).toContainEqual({
    method: "DELETE",
    path: DECISION,
    body: null,
  });

  await button(page, "Send for approval").click();
  await expect(button(page, "Withdraw request")).toBeVisible();
  expect(
    state.calls.filter((call) => call.method === "POST" && call.path === SUBMISSIONS),
  ).toHaveLength(2);
});

test("organizer reviews the submitted version, not the newer draft, and approves it", async ({
  page,
}) => {
  const state = await openClass(page, { as: "organizer", submission: "PENDING" });

  await page.getByRole("link", { name: "Original submitted quiz", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`${PREVIEW}$`));

  await expect(page.getByText("Original submitted question")).toBeVisible();
  await expect(page.getByText("Original correct answer")).toBeVisible();
  await expect(page.getByText("New draft question")).toHaveCount(0);

  await button(page, "Approve this version").click();

  // After the decision the page reflects it: status updated, no buttons left.
  await expect(page.getByText("Approved by Professor")).toBeVisible();
  await expect(button(page, "Approve this version")).toHaveCount(0);
  await expect(button(page, "Reject")).toHaveCount(0);
  expect(state.calls).toContainEqual({
    method: "PATCH",
    path: DECISION,
    body: { status: "APPROVED" },
  });
});

test("approving from the queue removes the row from Pending", async ({ page }) => {
  await openClass(page, { as: "organizer", submission: "PENDING" });

  await expect(page.getByRole("link", { name: "Original submitted quiz", exact: true })).toBeVisible();
  await button(page, "Approve").click();

  await expect(page.getByText("Nothing to review")).toBeVisible();
});

test("a stale submission can be reviewed and rejected but not approved", async ({
  page,
}) => {
  const state = await openClass(page, {
    as: "organizer",
    submission: "PENDING",
    stale: true,
  });

  await expect(page.getByText("· outdated")).toBeVisible();
  await expect(button(page, "Approve")).toBeDisabled();

  await page.goto(PREVIEW);
  await expect(page.getByText("Original submitted question")).toBeVisible();
  await expect(button(page, "Approve this version")).toBeDisabled();

  await button(page, "Reject").click();
  await expect(page.getByText("Rejected by Professor")).toBeVisible();
  expect(state.calls).toContainEqual({
    method: "PATCH",
    path: DECISION,
    body: { status: "REJECTED" },
  });
});

test("a refused decision shows the server's reason and changes nothing", async ({
  page,
}) => {
  await openClass(page, {
    as: "organizer",
    submission: "PENDING",
    failDecision: true,
    path: PREVIEW,
  });

  await button(page, "Approve this version").click();

  await expect(
    page.getByText("A newer published version of this quiz is available."),
  ).toBeVisible();
  await expect(page.getByText("Approved by Professor")).toHaveCount(0);
  await expect(button(page, "Approve this version")).toBeVisible();
});

test("a denied preview shows no questions and no decision buttons", async ({
  page,
}) => {
  await openClass(page, {
    as: "organizer",
    submission: "PENDING",
    previewDenied: true,
    path: PREVIEW,
  });

  await expect(page.getByText("Submission not found.")).toBeVisible();
  await expect(page.getByText("Original submitted question")).toHaveCount(0);
  await expect(button(page, "Approve this version")).toHaveCount(0);
});

test("the submitter can read their submission but cannot decide it", async ({
  page,
}) => {
  await openClass(page, { as: "member", submission: "PENDING", path: PREVIEW });

  await expect(page.getByText("Original submitted question")).toBeVisible();
  await expect(page.getByText("Waiting for approval")).toBeVisible();
  await expect(button(page, "Approve this version")).toHaveCount(0);
  await expect(button(page, "Reject")).toHaveCount(0);
});

test("class page and preview fit a phone screen", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });

  await openClass(page, { as: "member", submission: "PENDING" });
  // Rows is the default; on a phone it drops the Approval column.
  await expect(page.getByRole("link", { name: "Original submitted quiz", exact: true })).toBeVisible();
  await noHorizontalScroll(page);

  await button(page, "Cards").click();
  await expect(button(page, "Withdraw request")).toBeVisible();
  await noHorizontalScroll(page);

  await page.goto(PREVIEW);
  await expect(page.getByText("Original submitted question")).toBeVisible();
  await noHorizontalScroll(page);
});

test("each quiz row and card has an options menu that exports its questions", async ({
  page,
}) => {
  await openClass(page, { as: "member" });

  for (const layout of ["Rows", "Cards"]) {
    if (layout === "Cards") await button(page, "Cards").click();
    const menu = page.locator(".cl-quiz-options");
    await expect(menu).toHaveCount(1);
    await menu.locator("summary").click();
    await expect(page.getByRole("link", { name: "Hosting history" })).toBeVisible();
    await expect(button(page, "Duplicate quiz")).toBeVisible();
    await expect(button(page, "Archive quiz")).toBeVisible();

    const download = page.waitForEvent("download");
    await button(page, "Export questions (CSV)").click();
    const file = await download;
    expect(file.suggestedFilename()).toMatch(/-questions\.csv$/);
    const text = await (await file.createReadStream()).toArray();
    expect(Buffer.concat(text).toString()).toContain("New draft question");
  }
});

function quizRow(page, title) {
  return page.getByRole("row").filter({ hasText: title });
}

async function menuOptions(scope) {
  await scope.locator(".cl-quiz-options summary").click();
  const options = scope.locator(".cl-quiz-options .ui-row-options");
  await expect(options).toBeVisible();
  return options.locator("a, button").allInnerTexts();
}

test("the options menu only offers what the member can do with each quiz", async ({
  page,
}) => {
  await openClass(page, {
    as: "member",
    moreQuizzes: [
      {
        quiz_id: 11,
        title: "Shared quiz",
        author_id: 1,
        author_name: "Professor",
        my_access: "EDITOR",
      },
      { quiz_id: 12, title: "Archived quiz", status: "ARCHIVED" },
      { quiz_id: 13, title: "Empty quiz", question_count: 0 },
    ],
  });

  expect(await menuOptions(quizRow(page, "Original submitted quiz"))).toEqual([
    "Hosting history",
    "Duplicate quiz",
    "Export questions (CSV)",
    "Archive quiz",
  ]);
  await page.keyboard.press("Escape");
  // A collaborator can't see the owner's hosting history or archive it.
  expect(await menuOptions(quizRow(page, "Shared quiz"))).toEqual([
    "Duplicate quiz",
    "Export questions (CSV)",
  ]);
  await page.keyboard.press("Escape");
  expect(await menuOptions(quizRow(page, "Archived quiz"))).toEqual([
    "Hosting history",
    "Duplicate quiz",
    "Export questions (CSV)",
  ]);
  await page.keyboard.press("Escape");
  expect(await menuOptions(quizRow(page, "Empty quiz"))).toEqual([
    "Hosting history",
    "Duplicate quiz",
    "Archive quiz",
  ]);
});

test("an archived class offers no Duplicate, which the server would refuse", async ({
  page,
}) => {
  await openClass(page, { as: "member", classArchived: true });
  expect(await menuOptions(quizRow(page, "Original submitted quiz"))).not.toContain(
    "Duplicate quiz",
  );
});

test("archive asks first and only archives once confirmed", async ({ page }) => {
  const state = await openClass(page, { as: "member" });
  const row = quizRow(page, "Original submitted quiz");
  const archives = () =>
    state.calls.filter((call) => call.method === "PATCH" && call.path.endsWith("/archive"));

  await row.locator(".cl-quiz-options summary").click();
  await button(page, "Archive quiz").click();
  await button(page, "Keep it").click();
  expect(archives()).toHaveLength(0);

  await row.locator(".cl-quiz-options summary").click();
  await button(page, "Archive quiz").click();
  await page.getByRole("dialog").getByRole("button", { name: "Archive quiz" }).click();
  await expect.poll(() => archives().length).toBe(1);
});

test("a failed export shows why and downloads nothing", async ({ page }) => {
  for (const [quizDetail, message] of [
    ["error", "Could not load the quiz."],
    ["empty", "has no questions to export"],
  ]) {
    await openClass(page, { as: "member", quizDetail });
    let downloaded = false;
    page.on("download", () => {
      downloaded = true;
    });
    await quizRow(page, "Original submitted quiz").locator(".cl-quiz-options summary").click();
    await button(page, "Export questions (CSV)").click();
    await expect(page.getByRole("alert").filter({ hasText: message })).toBeVisible();
    expect(downloaded).toBe(false);
    await page.unrouteAll({ behavior: "ignoreErrors" });
  }
});

test("a menu on the last row of a sideways-scrolling table floats over the page", async ({
  page,
}) => {
  await page.setViewportSize({ width: 900, height: 800 });
  await openClass(page, {
    as: "member",
    moreQuizzes: [
      {
        quiz_id: 11,
        title: "Supercalifragilisticexpialidocious_Thermodynamics_Final_Review_Quiz",
      },
    ],
  });
  const wrap = page.locator(".cl-table-wrap");
  const scrolled = await wrap.evaluate((el) => {
    el.scrollLeft = el.scrollWidth;
    return el.scrollLeft;
  });
  expect(scrolled).toBeGreaterThan(0);

  const row = quizRow(page, "Supercalifragilistic");
  const heightBefore = (await wrap.boundingBox()).height;
  await row.locator(".cl-quiz-options summary").click();
  // The table keeps its scroll instead of spilling past the page...
  expect(await wrap.evaluate((el) => el.scrollLeft)).toBe(scrolled);
  await noHorizontalScroll(page);
  // ...the menu floats over the page, whole and on screen...
  await expect(row.locator(".ui-row-options")).toBeVisible();
  const menu = await row.locator(".ui-row-options").boundingBox();
  const viewport = page.viewportSize();
  expect(menu.y).toBeGreaterThanOrEqual(0);
  expect(menu.y + menu.height).toBeLessThanOrEqual(viewport.height);
  expect(menu.x).toBeGreaterThanOrEqual(0);
  expect(menu.x + menu.width).toBeLessThanOrEqual(viewport.width);
  await expect(button(page, "Archive quiz")).toBeVisible();
  // ...and the table doesn't grow to make room for it.
  expect((await wrap.boundingBox()).height).toBe(heightBefore);
});

test("the row says what a slow menu option is doing after the menu closes", async ({
  page,
}) => {
  await openClass(page, { as: "member" });
  let finish;
  const held = new Promise((resolve) => {
    finish = resolve;
  });
  await page.route("**/__test_api/quizzes/*", async (route) => {
    await held;
    await route.fallback();
  });
  const row = quizRow(page, "Original submitted quiz");
  await row.locator(".cl-quiz-options summary").click();
  await button(page, "Export questions (CSV)").click();
  await expect(row.getByRole("status")).toHaveText("Exporting…");

  const download = page.waitForEvent("download");
  finish();
  await download;
  await expect(row.getByRole("status")).toHaveCount(0);
});

test("a row menu opens downward and the table doesn't grow for it", async ({ page }) => {
  // Short enough that the first row has little room below it.
  await page.setViewportSize({ width: 494, height: 690 });
  await openClass(page, {
    as: "member",
    moreQuizzes: [
      { quiz_id: 11, title: "Second quiz" },
      { quiz_id: 12, title: "Third quiz" },
    ],
  });
  const wrap = page.locator(".cl-table-wrap");
  const height = (await wrap.boundingBox()).height;
  for (const title of ["Original submitted quiz", "Third quiz"]) {
    const row = quizRow(page, title);
    await row.locator(".cl-quiz-options summary").click();
    const options = row.locator(".ui-row-options");
    await expect(options).toBeVisible();
    const summary = await row.locator(".cl-quiz-options summary").boundingBox();
    expect((await options.boundingBox()).y).toBeGreaterThan(summary.y);
    expect((await wrap.boundingBox()).height).toBe(height);
    await page.keyboard.press("Escape");
  }
});
