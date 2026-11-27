import { expect, test } from "@playwright/test";

import { IDS, openClass } from "./workflow-fixture";

const { CLASS_ID, QUIZ_ID, SUBMISSION_ID, SUBMITTED_VERSION_ID } = IDS;
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
  const dialog = page.getByRole("dialog", { name: "Reject submission" });
  await expect(dialog.getByRole("textbox", { name: "Rejection comment (optional)" })).toBeFocused();
  await dialog.getByRole("button", { name: "Reject submission" }).click();
  await expect(page.getByText("Rejected by Professor")).toBeVisible();
  expect(state.calls).toContainEqual({
    method: "PATCH",
    path: DECISION,
    body: { status: "REJECTED" },
  });
});

for (const entry of ["queue", "preview"]) {
  test(`the ${entry} rejection form accepts exactly 1,000 trimmed characters`, async ({ page }) => {
    const state = await openClass(page, {
      as: "organizer", submission: "PENDING", path: entry === "preview" ? PREVIEW : undefined,
    });
    const reject = button(page, "Reject");
    await reject.focus();
    await page.keyboard.press("Enter");
    const dialog = page.getByRole("dialog", { name: "Reject submission" });
    const input = dialog.getByRole("textbox", { name: "Rejection comment (optional)" });
    const submit = dialog.getByRole("button", { name: "Reject submission" });
    await expect(input).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(dialog.getByRole("button", { name: "Cancel" })).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
    await expect(reject).toBeFocused();
    expect(state.calls.filter((call) => call.method === "PATCH")).toHaveLength(0);

    await reject.click();
    const boundary = "🧪".repeat(1000);
    await input.fill(`${boundary}x`);
    await expect(submit).toBeDisabled();
    await input.fill(`  ${boundary}  `);
    await expect(submit).toBeEnabled();
    await submit.click();
    await expect(dialog).toHaveCount(0);
    expect(state.calls).toContainEqual({
      method: "PATCH", path: DECISION, body: { status: "REJECTED", rejection_comment: boundary },
    });
  });

  test(`the ${entry} rejection form preserves feedback after a refused decision`, async ({ page }) => {
    const state = await openClass(page, {
      as: "organizer", submission: "PENDING", failDecision: true,
      path: entry === "preview" ? PREVIEW : undefined,
    });
    await button(page, "Reject").click();

    const dialog = page.getByRole("dialog", { name: "Reject submission" });
    const input = dialog.getByRole("textbox", { name: "Rejection comment (optional)" });
    const submit = dialog.getByRole("button", { name: "Reject submission" });
    await input.fill("x".repeat(1001));
    await expect(submit).toBeDisabled();
    await input.fill("  Revise the second question.  ");
    await submit.click();
    await expect(dialog.getByRole("alert")).toBeVisible();
    await expect(input).toHaveValue("  Revise the second question.  ");
    await submit.click();
    await expect.poll(() => state.calls.filter((call) => call.method === "PATCH" && call.path === DECISION)).toEqual(
      Array.from({ length: 2 }, () => ({
        method: "PATCH", path: DECISION,
        body: { status: "REJECTED", rejection_comment: "Revise the second question." },
      })),
    );
    await expect(submit).toBeEnabled();
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
    await expect(button(page, "Reject")).toBeFocused();
  });
}

test("a collaborator sees rejection feedback on the quiz page without preview access", async ({ page }) => {
  const comment = "Replace <b>the diagram</b> and add an explanation.";
  await openClass(page, { as: "collaborator", submission: "REJECTED", comment, previewDenied: true });

  await button(page, "Cards").click();
  await expect(page.getByRole("article").getByText("Rejected", { exact: true })).toBeVisible();
  await expect(page.getByText(comment, { exact: true })).toHaveCount(0);
  await button(page, "Rows").click();
  const quizzes = page.getByRole("table", { name: "My quizzes" });
  await expect(quizzes.getByRole("cell", { name: "Rejected", exact: true })).toHaveClass(/is-rejected/);
  await expect(quizzes.getByText(comment, { exact: true })).toHaveCount(0);
  await quizzes.getByRole("link", { name: "Original submitted quiz", exact: true }).click();
  const banner = page.getByRole("status").filter({ hasText: "Rejected by Professor" });
  await expect(banner.getByText(comment, { exact: true })).toBeVisible();

  await page.goto(PREVIEW);
  await expect(page.getByText("Submission not found.")).toBeVisible();
});

test("a saved edit refreshes the pending queue when the request is withdrawn", async ({ page }) => {
  let notifications;
  await page.routeWebSocket("**/ws/notifications", (socket) => {
    socket.onMessage(() => {
      notifications = socket;
      socket.send(JSON.stringify({ type: "notifications_ready" }));
    });
  });
  const state = await openClass(page, { as: "organizer", submission: "PENDING" });
  await expect(button(page, "Approve")).toBeVisible();
  await expect.poll(() => Boolean(notifications)).toBe(true);

  state.submission.status = "WITHDRAWN";
  notifications.send(JSON.stringify({
    type: "submission_changed", action: "withdrawn",
    class_id: CLASS_ID, quiz_id: QUIZ_ID, submission_id: SUBMISSION_ID,
  }));

  await expect(page.getByText("Nothing to review")).toBeVisible();
  await page.getByRole("combobox", { name: "Show submissions" }).selectOption("WITHDRAWN");
  await expect(page.getByRole("cell", { name: "Withdrawn", exact: true })).toBeVisible();
});

test("a collaborator sees Rejected after refocusing My quizzes", async ({ page }) => {
  const now = Date.now();
  await page.clock.setFixedTime(now);
  const state = await openClass(page, { as: "collaborator", submission: "PENDING" });
  await expect(button(page, "Waiting for approval")).toBeVisible();
  const comment = "Clarify which units the answer should use.";

  state.submission.status = "REJECTED";
  state.submission.rejection_comment = comment;
  await page.clock.setFixedTime(now + 11_000);
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));

  await expect(page.getByText("Rejected", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: "Original submitted quiz", exact: true }).click();
  await expect(page.getByText(comment, { exact: true })).toBeVisible();
});

for (const width of [375, 1280]) {
  test(`long feedback fits the quiz page at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 812 });
    const comment = `<img src=x alt="literal feedback"> ${"longword".repeat(108)}`;
    await openClass(page, {
      as: "collaborator", submission: "REJECTED", comment, path: `/app/quizzes/${QUIZ_ID}`,
    });
    const banner = page.getByRole("status").filter({ hasText: "Rejected by Professor" });
    await expect(banner.getByText(comment, { exact: true })).toBeVisible();
    await expect(page.getByRole("img", { name: "literal feedback" })).toHaveCount(0);
    await noHorizontalScroll(page);
  });

  test(`Participate shows a host and zero-score player with links at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 812 });
    await openClass(page, {
      path: `/app/classes/${CLASS_ID}?section=Reports`,
      sessions: [
        { session_id: 20, quiz_title: "My hosted quiz", host_name: "Student", is_host: true },
        {
          session_id: 21, quiz_title: "Quiz I played", host_name: "Professor",
          is_host: false, my_score: 0, my_rank: 1, participant_count: 1,
        },
        { session_id: 22, quiz_title: "Quiz I missed", host_name: "Professor", is_host: false },
      ],
    });
    await button(page, "Cards").click();
    const hostPath = "/app/results/host/20";
    const playerPath = `/app/classes/${CLASS_ID}/sessions/21/report`;
    const hostedCard = page.getByRole("article").filter({ hasText: "My hosted quiz" });
    await expect(hostedCard.getByText("Hosted", { exact: true })).toBeVisible();
    await expect(hostedCard.getByRole("link")).toHaveAttribute("href", hostPath);
    await expect(hostedCard.getByText(/Rank #|points|No score recorded/)).toHaveCount(0);
    const playedCard = page.getByRole("article").filter({ hasText: "Quiz I played" });
    await expect(playedCard.getByText("0 points")).toBeVisible();
    await expect(playedCard.getByRole("link")).toHaveAttribute("href", playerPath);
    await noHorizontalScroll(page);

    await button(page, "Rows").click();
    const hostedRow = page.getByRole("row").filter({ hasText: "My hosted quiz" });
    await expect(hostedRow.getByRole("cell", { name: "Hosted", exact: true })).toBeVisible();
    await expect(hostedRow.getByRole("link", { name: "My hosted quiz", exact: true })).toHaveAttribute("href", hostPath);
    const playedRow = page.getByRole("row").filter({ hasText: "Quiz I played" });
    await expect(playedRow.getByRole("link", { name: "Quiz I played", exact: true })).toHaveAttribute("href", playerPath);
    const missedRow = page.getByRole("row").filter({ hasText: "Quiz I missed" });
    await expect(missedRow.getByRole("cell", { name: "Absent", exact: true })).toBeVisible();
    await expect(missedRow.getByRole("link")).toHaveCount(0);
    await noHorizontalScroll(page);
  });
}

test("withdrawal refresh and window focus preserve unsaved editor text", async ({ page }) => {
  const now = Date.now();
  await page.clock.setFixedTime(now);
  let notifications;
  await page.routeWebSocket("**/ws/notifications", (socket) => {
    socket.onMessage(() => {
      notifications = socket;
      socket.send(JSON.stringify({ type: "notifications_ready" }));
    });
  });
  const state = await openClass(page, { path: `/app/quizzes/${QUIZ_ID}/edit`, submission: "PENDING" });
  const title = page.getByRole("textbox", { name: "Quiz title" });
  await title.fill("Unsaved title I am still editing");
  await expect.poll(() => Boolean(notifications)).toBe(true);

  state.submission.status = "WITHDRAWN";
  state.quizRevision += 1;
  notifications.send(JSON.stringify({
    type: "submission_changed", action: "withdrawn",
    class_id: CLASS_ID, quiz_id: QUIZ_ID, submission_id: SUBMISSION_ID,
  }));
  await page.clock.setFixedTime(now + 11_000);
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));

  await expect(title).toHaveValue("Unsaved title I am still editing");
  expect(state.calls.filter((call) => call.path === `/quizzes/${QUIZ_ID}`).map((call) => call.method))
    .toEqual(["GET"]);
});

const STUDENT_REPORT = {
  account_id: 2,
  display_name: "Student",
  session_count: 1,
  attendance_session_count: 2,
  attendance_rate: 0.5,
  total_points: 0,
  average_score: 0,
  sessions: [
    { session_id: 20, quiz_title: "My hosted quiz", attendance_status: "HOSTED", played: false },
    {
      session_id: 21, quiz_title: "Quiz I played", attendance_status: "PLAYED",
      played: true, points: 0, rank: 1, correct: 0, incorrect: 1,
    },
    { session_id: 22, quiz_title: "Quiz I missed", attendance_status: "ABSENT", played: false },
  ],
};
const STUDENT_REPORT_PATH = `/app/classes/${CLASS_ID}/students/2/report`;

test("a student report URL redirects students to their class Reports tab", async ({ page }) => {
  const state = await openClass(page, { path: STUDENT_REPORT_PATH });
  await expect(page).toHaveURL((url) =>
    url.pathname === `/app/classes/${CLASS_ID}` && url.searchParams.get("section") === "Reports"
  );
  expect(state.calls.some(({ path }) => path.includes("/students/2/results"))).toBe(false);
  await expect(page.getByRole("region", { name: "Report summary" })).toHaveCount(0);
});

test("the organizer roster aligns recent statuses and opens class reports", async ({ page }) => {
  const studentReport = { ...STUDENT_REPORT, view: "organizer" };
  await openClass(page, {
    as: "organizer",
    path: `/app/classes/${CLASS_ID}?view=admin&section=Students`,
    studentReport,
    studentStats: [{
      ...studentReport, recent_scores: [null, 0, null],
      recent_attendance_statuses: ["HOSTED", "PLAYED", "ABSENT"],
    }],
  });
  const recent = page.getByRole("group", { name: "Recent attendance, oldest to newest" });
  await expect(recent.locator("span")).toHaveText(["–", "0", "–"]);
  await button(page, "Show Student's details").click();
  await expect(page.getByText(/50% attendance · 2 eligible sessions/)).toBeVisible();

  const hosted = page.getByRole("table", { name: "Student's presentations" })
    .getByRole("row").filter({ hasText: "My hosted quiz" });
  await expect(hosted.getByRole("cell", { name: "Hosted", exact: true })).toBeVisible();
  await expect(hosted.getByRole("link")).toHaveCount(0);
  const expanded = page.getByRole("table", { name: "Student's presentations" });
  await expect(expanded.getByRole("row", { name: /Quiz I missed/ }).getByRole("link")).toHaveCount(0);
  await expect(expanded.getByRole("row", { name: /Quiz I played/ }).getByRole("link"))
    .toHaveAttribute("href", `/app/classes/${CLASS_ID}/sessions/21/report`);

  await page.getByRole("link", { name: /Full report/ }).click();
  const fullReport = page.getByRole("table", { name: "Student session history" });
  await expect(fullReport.getByRole("row", { name: /My hosted quiz/ }).getByRole("link")).toHaveCount(0);
});

test("the professor can scroll to Results in the expanded student panel on a phone", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await openClass(page, {
    as: "organizer",
    path: `/app/classes/${CLASS_ID}?view=admin&section=Students`,
    studentReport: { ...STUDENT_REPORT, view: "organizer" },
  });
  await button(page, "Show Student's details").click();
  const panel = page.getByRole("region", { name: "Student presentations" });
  const results = panel.getByRole("link", { name: /Results/ });
  await expect(results).toBeVisible();
  await results.scrollIntoViewIfNeeded();
  await expect(results).toBeInViewport();
  await expect.poll(() => panel.evaluate((element) => element.scrollLeft)).toBeGreaterThan(0);
  await noHorizontalScroll(page);
});

test("a professor sees null attendance for a student who only hosted", async ({ page }) => {
  await openClass(page, {
    as: "organizer",
    path: STUDENT_REPORT_PATH,
    studentReport: {
      ...STUDENT_REPORT, view: "organizer", attendance_rate: null,
      attendance_session_count: 0, session_count: 0, sessions: [STUDENT_REPORT.sessions[0]],
    },
  });
  await expect(page.getByText("No eligible sessions")).toBeVisible();
  await expect(page.getByRole("cell", { name: "Hosted", exact: true })).toBeVisible();
});

test("the submitted version preview displays returned feedback", async ({ page }) => {
  const comment = "The example needs a correction.";
  await openClass(page, { as: "organizer", submission: "REJECTED", comment, path: PREVIEW });

  await expect(page.getByText("Original submitted question")).toBeVisible();
  await expect(page.getByText(comment, { exact: true })).toBeVisible();
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
  // The title opens the quiz, so the row has no separate arrow.
  await expect(page.locator(".cl-member-rows a.cl-go")).toHaveCount(0);

  for (const layout of ["Rows", "Cards"]) {
    if (layout === "Cards") await button(page, "Cards").click();
    const menu = page.locator(".cl-quiz-options");
    await expect(menu).toHaveCount(1);
    const pageHeight = await page.evaluate(() => document.body.offsetHeight);
    await menu.locator("summary").click();
    // It opens downward without stretching the page to make room.
    const options = menu.locator(".ui-row-options");
    await expect(options).toBeVisible();
    expect((await options.boundingBox()).y).toBeGreaterThan(
      (await menu.locator("summary").boundingBox()).y,
    );
    expect(await page.evaluate(() => document.body.offsetHeight)).toBe(pageHeight);
    const history = page.getByRole("link", { name: "Hosting history" });
    await expect(history).toBeVisible();
    // The link looks like the buttons beside it.
    const color = (item) => item.evaluate((el) => getComputedStyle(el).color);
    expect(await color(history)).toBe(await color(button(page, "Duplicate quiz")));
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

test("a member of an archived class sees no quizzes and no options menu", async ({
  page,
}) => {
  await openClass(page, {
    as: "member",
    classArchived: true,
    quiz: { my_access: "EDITOR", question_count: 0 },
  });

  // Only organizers can open an archived class's quizzes.
  await expect(page.getByText("This class is archived.")).toBeVisible();
  await expect(page.getByRole("link", { name: "Original submitted quiz", exact: true })).toHaveCount(0);
  await expect(page.locator(".cl-quiz-options")).toHaveCount(0);
  await expect(button(page, "Cards")).toHaveCount(0);
});
