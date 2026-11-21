import { expect } from "@playwright/test";
import { test, watchSocket } from "./full-stack-fixture.js";

function button(page, name) {
  return page.getByRole("button", { name });
}

const approve = (classPath) => `/app${classPath}?view=admin&section=Approvals`;
const myQuizzes = (classPath) => `/app${classPath}?view=user&section=My%20quizzes`;
const quizPage = (quiz) => `/app/quizzes/${quiz.quiz_id}`;

async function createQuiz(course, person, title, prompt) {
  return course.rest(person, "POST", `${course.classPath}/quizzes`, {
    title,
    questions: [{
      question_text: prompt,
      time_limit_seconds: 30,
      base_points: 1000,
      choices: [
        { choice_text: "Correct choice", is_correct: true },
        { choice_text: "Wrong choice", is_correct: false },
      ],
    }],
  });
}

async function approvedQuiz(course, person, title, prompt) {
  const draft = await createQuiz(course, person, title, prompt);
  const published = await course.rest(person, "POST", `${course.classPath}/quizzes/${draft.quiz_id}/publish`, {
    expected_revision: draft.revision,
  });
  const request = await course.rest(person, "POST", `${course.classPath}/quiz-submissions`, {
    quiz_version_id: published.version.quiz_version_id,
  });
  await course.rest(course.organizer, "PATCH", `${course.classPath}/quiz-submissions/${request.submission_id}`, {
    status: "APPROVED",
  });
  return published;
}

test("an organizer edit withdraws a submitted snapshot and the owner can resubmit for approval", async ({ course }) => {
  const { classPath, organizer, owner, newAccountPage } = course;
  const submittedTitle = "Review this submission";
  const editedTitle = "Review the saved revision";
  const prompt = "Which question was submitted?";
  const quiz = await createQuiz(course, owner, submittedTitle, prompt);

  const queue = await newAccountPage(organizer);
  const notification = watchSocket(queue, "/ws/notifications");
  await queue.goto(approve(classPath));
  await notification({ type: "notifications_ready" });
  await expect(queue.getByText("Nothing to review")).toBeVisible();

  const author = await newAccountPage(owner);
  await author.goto(quizPage(quiz));
  await button(author, /Send for approval/).click();
  await notification({ type: "submission_changed", action: "submitted", quiz_id: quiz.quiz_id });
  const submitted = queue.getByRole("link", { name: submittedTitle, exact: true });
  await expect(submitted).toBeVisible();
  const previewPath = await submitted.getAttribute("href");

  // Keep the first organizer tab on the queue. Watch it update while the
  // second tab uses the quiz editor, without reloading the queue.
  const preview = await queue.context().newPage();
  const editorSocket = watchSocket(preview, `/ws/quizzes/${quiz.quiz_id}`);
  await preview.goto(previewPath);
  await expect(preview.getByRole("heading", { name: submittedTitle })).toBeVisible();
  await expect(preview.getByText(prompt, { exact: true })).toBeVisible();
  await preview.getByRole("link", { name: "Edit quiz" }).click();
  await expect(preview).toHaveURL(new RegExp(`${quizPage(quiz)}/edit$`));
  await editorSocket({ type: "quiz_editor_state" });
  await expect(button(preview, /Send for approval/)).toHaveCount(0);
  await preview.getByRole("textbox", { name: "Quiz title" }).fill(editedTitle);
  await button(preview, "Save changes").click();
  await expect(preview.getByRole("heading", { name: editedTitle })).toBeVisible();

  await notification({ type: "submission_changed", action: "withdrawn", quiz_id: quiz.quiz_id, status: "WITHDRAWN" });
  await expect(queue.getByText("Nothing to review")).toBeVisible();
  await preview.goto(previewPath);
  await expect(preview.getByRole("heading", { name: submittedTitle })).toBeVisible();
  await expect(preview.getByText("Withdrawn by Prof")).toBeVisible();

  await author.goto(myQuizzes(classPath));
  await expect(author.getByText("Withdrawn", { exact: true })).toBeVisible();
  await button(author, "Send for approval").click();
  await queue.getByRole("link", { name: editedTitle, exact: true }).click();
  await expect(queue.getByRole("heading", { name: editedTitle })).toBeVisible();
  await button(queue, "Approve this version").click();
  await expect(queue.getByText("Approved by Prof")).toBeVisible();
});

test("rejection feedback reaches eligible readers without expanding preview access", async ({ course }) => {
  const { classPath, organizer, owner, collaborator, unrelated, newAccountPage } = course;
  const title = "Quiz with feedback";
  const feedback = "Clarify <b>the example</b> in the first question.";
  const quiz = await createQuiz(course, owner, title, "Which example fits?");
  await course.rest(owner, "POST", `${classPath}/quizzes/${quiz.quiz_id}/collaborators`, {
    email: course.accounts[collaborator].email,
  });

  const author = await newAccountPage(owner);
  const coeditor = await newAccountPage(collaborator);
  const reviewer = await newAccountPage(organizer);
  const classmate = await newAccountPage(unrelated);
  await author.goto(myQuizzes(classPath));
  await button(author, "Send for approval").click();
  await expect(button(author, "Withdraw request")).toBeVisible();

  await reviewer.goto(approve(classPath));
  await reviewer.getByRole("link", { name: title, exact: true }).click();
  await expect(reviewer.getByRole("heading", { name: title })).toBeVisible();
  const previewPath = new URL(reviewer.url()).pathname;
  await button(reviewer, /^Reject$/).click();
  const dialog = reviewer.getByRole("dialog", { name: "Reject submission" });
  await dialog.getByRole("textbox", { name: "Rejection comment (optional)" }).fill(feedback);
  await button(dialog, "Reject submission").click();
  await expect(reviewer.getByText("Rejected by Prof")).toBeVisible();
  await expect(reviewer.getByText(feedback, { exact: true })).toBeVisible();

  await expect(author.getByText(feedback, { exact: true })).toBeVisible();
  await coeditor.goto(myQuizzes(classPath));
  await expect(coeditor.getByText(feedback, { exact: true })).toBeVisible();
  await coeditor.goto(previewPath);
  await expect(coeditor.getByRole("alert")).toContainText("Submission not found");
  await expect(coeditor.getByText(feedback, { exact: true })).toHaveCount(0);

  await classmate.goto(myQuizzes(classPath));
  await expect(classmate.getByText("No quizzes yet")).toBeVisible();
  await expect(classmate.getByText(feedback, { exact: true })).toHaveCount(0);
  await classmate.goto(previewPath);
  await expect(classmate.getByRole("alert")).toContainText("Submission not found");
});

async function finishSession({ host, player, quiz, prompt, answer }) {
  const completion = watchSocket(host, "/ws/sessions/");
  await host.goto(quizPage(quiz));
  const started = host.waitForResponse((response) =>
    response.request().method() === "POST" &&
    new URL(response.url()).pathname.endsWith(`/quizzes/${quiz.quiz_id}/sessions`) &&
    response.ok(),
  );
  await button(host, /^Host live/).click();
  const { session_id: id, join_code: code } = await (await started).json();

  const participantSocket = watchSocket(player, `/ws/sessions/${id}`);
  await player.goto("/app/join");
  await player.getByRole("textbox", { name: "Session code" }).fill(code);
  await button(player, /^Join /).click();
  await expect(player).toHaveURL(new RegExp(`/app/play/${id}$`));
  await participantSocket({ type: "session_state" });
  await button(host, /Start quiz/).click();
  await expect(host.getByRole("heading", { name: prompt, exact: true })).toBeVisible();
  await button(player, new RegExp(answer)).click();
  await button(host, /Finish quiz/).click();
  const confirm = host.getByRole("dialog", { name: "That was the last question." });
  await button(confirm, "End session").click();
  await expect(host.getByRole("heading", { name: "Final results" })).toBeVisible();
  await expect(player.getByText("Quiz complete", { exact: true })).toBeVisible();
  await completion({ type: "session_ended", reason: "COMPLETED" });
  return id;
}

test("live results differentiate Hosted, zero-point Played, and Absent and retain old questions", async ({ course }) => {
  const { classPath, accounts, organizer, owner, collaborator, newAccountPage } = course;
  const historicalQuestion = "What was the original prompt?";
  const revisedQuestion = "What is the newer prompt?";
  const hosted = await approvedQuiz(course, owner, "Student-hosted round", historicalQuestion);
  const played = await approvedQuiz(course, organizer, "Zero-point round", "Which choice earns a point?");
  const missed = await approvedQuiz(course, organizer, "Missed round", "Which round did the student miss?");
  const student = await newAccountPage(owner);
  const reviewer = await newAccountPage(organizer);
  const coeditor = await newAccountPage(collaborator);

  const hostedId = await finishSession({
    host: student, player: coeditor, quiz: hosted, prompt: historicalQuestion, answer: "Correct choice",
  });
  await finishSession({
    host: reviewer, player: student, quiz: played, prompt: "Which choice earns a point?", answer: "Wrong choice",
  });
  await finishSession({
    host: reviewer, player: coeditor, quiz: missed, prompt: "Which round did the student miss?", answer: "Correct choice",
  });

  await student.goto(`${quizPage(hosted)}/edit`);
  await student.getByRole("textbox", { name: "Question 1 text" }).fill(revisedQuestion);
  await button(student, "Save changes").click();
  await expect(student.getByText(revisedQuestion, { exact: true })).toBeVisible();

  await student.goto(`/app${classPath}/students/${accounts[owner].account_id}/report`);
  const summary = student.getByRole("region", { name: "Report summary" });
  await expect(summary.getByText("50%", { exact: true })).toBeVisible();
  await expect(summary.getByText("Sessions played", { exact: true }).locator("..")).toHaveText("Sessions played1");
  await expect(summary.getByText("Eligible sessions", { exact: true }).locator("..")).toHaveText("Eligible sessions2");

  const hostRow = student.getByRole("row", { name: /Student-hosted round/ });
  await expect(hostRow.getByRole("cell", { name: "Hosted", exact: true })).toBeVisible();
  const playedRow = student.getByRole("row", { name: /Zero-point round/ });
  await expect(playedRow.getByRole("cell", { name: "Played", exact: true })).toBeVisible();
  await expect(playedRow.getByRole("cell", { name: "0", exact: true })).toHaveCount(2);
  const missedRow = student.getByRole("row", { name: /Missed round/ });
  await expect(missedRow.getByRole("cell", { name: "Absent", exact: true })).toBeVisible();
  await expect(missedRow.getByRole("link")).toHaveCount(0);

  await student.goto(`/app${classPath}?view=user&section=Reports`);
  const hostedLink = student.getByRole("link", { name: "Student-hosted round", exact: true });
  await expect(hostedLink).toHaveAttribute("href", `/app/results/host/${hostedId}`);
  await hostedLink.click();
  await expect(student.getByRole("heading", { name: "Student-hosted round" })).toBeVisible();
  await button(student, "Questions").click();
  await expect(student.getByText(historicalQuestion, { exact: true })).toBeVisible();
  await expect(student.getByText(revisedQuestion, { exact: true })).toHaveCount(0);
});
