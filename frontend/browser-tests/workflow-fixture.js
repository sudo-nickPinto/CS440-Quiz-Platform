export async function openWorkflow(page, options = {}) {
  const {
    organizer = false,
    initialStatus = null,
    blocked = false,
    previewDenied = false,
    failDecision = false,
    count = 1,
  } = options;

  const time = "2026-11-10T12:00:00Z";

  const question = {
    question_id: 1000,
    question_order: 1,
    question_type: "MULTIPLE_CHOICE",
    question_text: "Original submitted question",
    explanation: "Original explanation",
    time_limit_seconds: 20,
    base_points: 1000,
    revision: 1,
    choices: [
      {
        choice_id: 1,
        choice_order: 1,
        choice_text: "Original correct answer",
        is_correct: true,
      },
      {
        choice_id: 2,
        choice_order: 2,
        choice_text: "Wrong answer",
        is_correct: false,
      },
    ],
  };

  // When testing a pending submission, expose a newer draft in the
  // ordinary quiz endpoint. The preview must still show submitted v1.
  const newerDraft = initialStatus === "PENDING";

  const quizzes = Array.from({ length: count }, (_, index) => ({
    quiz_id: 10 + index,
    class_id: 4,
    author_id: 2,
    author_name: "Student",
    status: newerDraft ? "DRAFT" : "PUBLISHED",
    can_edit: !organizer,
    updated_at: time,
    version: {
      quiz_version_id: newerDraft ? 200 + index : 100 + index,
      version_number: newerDraft ? 2 : 1,
      title: count === 1 ? "Test quiz" : `Quiz ${index + 1}`,
      description: null,
      created_at: time,
      published_at: newerDraft ? null : time,
      questions: [
        newerDraft
          ? { ...question, question_text: "New draft question" }
          : question,
      ],
    },
  }));

  const submittedVersion = {
    ...quizzes[0].version,
    quiz_version_id: 100,
    version_number: 1,
    title: "Original submitted quiz",
    published_at: time,
    questions: [question],
  };

  const state = {
    calls: [],
    submission: initialStatus
      ? {
          submission_id: 50,
          class_id: 4,
          quiz_version_id: 100,
          submitted_by_id: 2,
          status: initialStatus,
          submitted_at: time,
          decided_at: null,
          decided_by_id: null,
        }
      : null,
  };

  await page.route("**/__test_api/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname.replace("/__test_api", "");
    const method = request.method();
    const body = request.postData() ? request.postDataJSON() : null;

    state.calls.push({ method, path, body });

    const json = (value, status = 200) =>
      route.fulfill({ status, json: value });

    const error = (status, code, message) =>
      json({ error: { code, message } }, status);

    if (method === "GET" && path === "/classes/4") {
      return json({
        class_id: 4,
        name: "Browser test class",
        current_role: organizer ? "ORGANIZER" : "MEMBER",
        membership_status: "ACTIVE",
        archived_at: null,
        join_code: "TEST1234",
        joining_open: true,
      });
    }

    if (method === "GET" && path === "/classes/4/quizzes") {
      return json({
        class_id: 4,
        items: quizzes,
        pagination: {
          page: 1,
          page_size: 100,
          total_items: quizzes.length,
          total_pages: 1,
        },
      });
    }

    const quiz = quizzes.find(
      (item) => path === `/classes/4/quizzes/${item.quiz_id}`,
    );

    if (method === "GET" && quiz) return json(quiz);

    if (path === "/classes/4/quiz-submissions") {
      if (method === "GET") {
        return json(state.submission ? [state.submission] : []);
      }

      if (method === "POST") {
        state.submission = {
          submission_id: 50,
          class_id: 4,
          quiz_version_id: body.quiz_version_id,
          submitted_by_id: 2,
          status: "PENDING",
          submitted_at: time,
          decided_at: null,
          decided_by_id: null,
        };

        return json(state.submission, 201);
      }
    }

    if (method === "GET" && path === "/classes/4/quiz-submissions/50/preview") {
      if (previewDenied) {
        return error(404, "submission_not_found", "Submission not found.");
      }

      return json({
        submission: state.submission,
        quiz_id: 10,
        submitted_by_name: "Student",
        version: submittedVersion,
        can_approve:
          organizer && !blocked && state.submission.status === "PENDING",
        approval_block_reason: blocked
          ? "A newer published version of this quiz is available."
          : null,
      });
    }

    if (path === "/classes/4/quiz-submissions/50") {
      if (method === "PATCH") {
        if (failDecision) {
          return error(
            409,
            "quiz_version_stale",
            "A newer published version of this quiz is available.",
          );
        }

        state.submission.status = body.status;
        state.submission.decided_at = time;
        state.submission.decided_by_id = 1;
        return json(state.submission);
      }

      if (method === "DELETE") {
        state.submission.status = "WITHDRAWN";
        return route.fulfill({ status: 204 });
      }
    }

    if (method === "GET" && path === "/classes/4/approved-quizzes") {
      return json(
        state.submission?.status === "APPROVED"
          ? [
              {
                submission_id: 50,
                quiz_id: 10,
                quiz_version_id: 100,
                version_number: 1,
                title: "Original submitted quiz",
                author_id: 2,
                approved_at: time,
                approved_by_id: 1,
              },
            ]
          : [],
      );
    }

    if (method === "POST" && path === "/classes/4/quizzes/10/sessions") {
      return json({ session_id: 77 }, 201);
    }

    return error(500, "unhandled_test_request", `${method} ${path}`);
  });

  await page.goto(organizer ? "/?role=organizer" : "/");
  await page
    .getByRole("heading", {
      name: "Browser test class: Quizzes",
    })
    .waitFor();

  return state;
}
