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

  await page.getByRole("link", { name: "Original submitted quiz" }).click();
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

  await expect(page.getByRole("link", { name: "Original submitted quiz" })).toBeVisible();
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
  await expect(button(page, "Withdraw request")).toBeVisible();
  await noHorizontalScroll(page);

  await page.goto(PREVIEW);
  await expect(page.getByText("Original submitted question")).toBeVisible();
  await noHorizontalScroll(page);
});
