import { test, expect } from "@playwright/test";
import { openWorkflow } from "./workflow-fixture";

async function confirm(page, buttonName) {
  await page
    .getByRole("dialog")
    .getByRole("button", { name: buttonName, exact: true })
    .click();
}

async function review(page) {
  await page
    .getByRole("button", {
      name: "Review submissions",
      exact: true,
    })
    .click();

  await page
    .getByRole("button", {
      name: "Review submitted version",
      exact: true,
    })
    .click();

  return page.getByRole("region", {
    name: "Submitted version preview",
  });
}

test("member submits, withdraws, and resubmits a version", async ({ page }) => {
  const state = await openWorkflow(page);

  await page
    .getByRole("button", {
      name: "Submit for approval",
    })
    .click();
  await confirm(page, "Submit");

  await expect(
    page.getByText("Quiz version submitted for approval."),
  ).toBeVisible();

  expect(state.calls).toContainEqual({
    method: "POST",
    path: "/classes/4/quiz-submissions",
    body: { quiz_version_id: 100 },
  });

  await page
    .getByRole("button", {
      name: "My submissions",
      exact: true,
    })
    .click();

  await expect(
    page.getByRole("button", {
      name: "Approve",
      exact: true,
    }),
  ).toHaveCount(0);

  await page
    .getByRole("button", {
      name: "Withdraw",
      exact: true,
    })
    .click();
  await confirm(page, "Withdraw");

  await expect(
    page.locator(".qw-badge").filter({
      hasText: /^WITHDRAWN$/,
    }),
  ).toBeVisible();

  await page
    .getByRole("button", {
      name: "My quizzes",
      exact: true,
    })
    .click();

  await page
    .getByRole("button", {
      name: "Submit for approval",
    })
    .click();
  await confirm(page, "Submit");

  await expect(
    page.getByText("Quiz version submitted for approval."),
  ).toBeVisible();

  expect(
    state.calls.filter(
      (call) =>
        call.method === "POST" && call.path === "/classes/4/quiz-submissions",
    ),
  ).toHaveLength(2);
});

test("organizer reviews original version, approves, and hosts", async ({
  page,
}) => {
  const state = await openWorkflow(page, {
    organizer: true,
    initialStatus: "PENDING",
  });

  await page
    .getByRole("button", {
      name: "Review submissions",
      exact: true,
    })
    .click();

  await expect(
    page.getByRole("button", {
      name: "Approve",
      exact: true,
    }),
  ).toBeDisabled();

  await page
    .getByRole("button", {
      name: "Review submitted version",
    })
    .click();

  const preview = page.getByRole("region", {
    name: "Submitted version preview",
  });

  await expect(preview).toContainText("Original submitted question");
  await expect(preview).toContainText("Original correct answer");
  await expect(preview).not.toContainText("New draft question");

  await page
    .getByRole("button", {
      name: "Approve",
      exact: true,
    })
    .click();
  await confirm(page, "Approve");

  await expect(page.getByText("Quiz version approved.")).toBeVisible();

  await page
    .getByRole("button", {
      name: "Approved quizzes",
      exact: true,
    })
    .click();

  await page
    .getByRole("button", {
      name: "Host live session",
      exact: true,
    })
    .click();

  await expect(
    page.getByRole("heading", {
      name: "Host route reached",
    }),
  ).toBeVisible();

  expect(state.calls).toContainEqual({
    method: "PATCH",
    path: "/classes/4/quiz-submissions/50",
    body: { status: "APPROVED" },
  });

  expect(state.calls).toContainEqual({
    method: "POST",
    path: "/classes/4/quizzes/10/sessions",
    body: null,
  });
});

test("stale versions remain reviewable but cannot be approved", async ({
  page,
}) => {
  await openWorkflow(page, {
    organizer: true,
    initialStatus: "PENDING",
    blocked: true,
  });

  const preview = await review(page);

  await expect(preview).toContainText("Original submitted question");
  await expect(preview).toContainText("A newer published version");

  await expect(
    page.getByRole("button", {
      name: "Approve",
      exact: true,
    }),
  ).toBeDisabled();

  await page
    .getByRole("button", {
      name: "Reject",
      exact: true,
    })
    .click();
  await confirm(page, "Reject");

  await expect(page.getByText("Submission rejected.")).toBeVisible();
});

test("preview access failure does not expose questions or enable approval", async ({
  page,
}) => {
  await openWorkflow(page, {
    organizer: true,
    initialStatus: "PENDING",
    previewDenied: true,
  });

  await review(page);

  await expect(page.getByText("Submission not found.")).toBeVisible();
  await expect(page.getByText("Original submitted question")).toHaveCount(0);

  await expect(
    page.getByRole("button", {
      name: "Approve",
      exact: true,
    }),
  ).toBeDisabled();
});

test("approval race displays the backend error without claiming success", async ({
  page,
}) => {
  await openWorkflow(page, {
    organizer: true,
    initialStatus: "PENDING",
    failDecision: true,
  });

  await review(page);

  await page
    .getByRole("button", {
      name: "Approve",
      exact: true,
    })
    .click();
  await confirm(page, "Approve");

  await expect(
    page.getByText("A newer published version of this quiz is available."),
  ).toBeVisible();

  await expect(page.getByText("Quiz version approved.")).toHaveCount(0);
});

test("pagination and filtering work on a narrow display", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openWorkflow(page, { count: 13 });

  await expect(page.locator(".qw-card")).toHaveCount(12);

  await page
    .getByRole("button", {
      name: "Next",
      exact: true,
    })
    .click();

  await expect(page.locator(".qw-card")).toHaveCount(1);

  await page.getByRole("searchbox").fill("Quiz 13");

  await expect(page.locator(".qw-card")).toHaveCount(1);
  await expect(
    page.getByRole("heading", {
      name: "Quiz 13",
      exact: true,
    }),
  ).toBeVisible();

  const hasHorizontalOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth > window.innerWidth + 1,
  );

  expect(hasHorizontalOverflow).toBe(false);
});
