// A small in-memory stand-in for the backend, answered through Playwright
// request interception. It only implements what the class page, approval
// queue and submission preview call, using the response shapes in
// backend/app/schemas. The backend tests remain responsible for the real
// authorization and version rules; these tests check what the screens do
// with those responses.

const CLASS_ID = 4;
const QUIZ_ID = 10;
const SUBMITTED_VERSION_ID = 100;
const SUBMISSION_ID = 50;
const TIME = "2026-11-10T12:00:00Z";

const PEOPLE = {
  organizer: { account_id: 1, role: "ADMIN", display_name: "Professor" },
  member: { account_id: 2, role: "USER", display_name: "Student" },
};

function page(items) {
  return {
    items,
    pagination: {
      page: 1,
      page_size: 25,
      total_items: items.length,
      total_pages: items.length ? 1 : 0,
    },
  };
}

function question(text, correct) {
  return {
    question_id: 1000,
    question_order: 1,
    question_type: "MULTIPLE_CHOICE",
    question_text: text,
    explanation: "Original explanation",
    time_limit_seconds: 20,
    base_points: 1000,
    revision: 1,
    choices: [
      { choice_id: 1, choice_order: 1, choice_text: correct, is_correct: true },
      { choice_id: 2, choice_order: 2, choice_text: "Wrong answer", is_correct: false },
    ],
  };
}

const SUBMITTED_VERSION = {
  quiz_version_id: SUBMITTED_VERSION_ID,
  version_number: 1,
  title: "Original submitted quiz",
  description: null,
  created_at: TIME,
  published_at: TIME,
  questions: [question("Original submitted question", "Original correct answer")],
};

/**
 * Opens the class page as the organizer or a member.
 *
 * options:
 *   as            "organizer" | "member"
 *   submission    null, or the initial status of submission 50
 *                 ("PENDING", "APPROVED", ...)
 *   stale         the submitted version is no longer the newest published
 *   previewDenied the preview endpoint answers 404
 *   failDecision  PATCH answers 409 quiz_version_stale
 *   path          where to start (defaults to the right class tab)
 */
export async function openClass(page_, options = {}) {
  const {
    as = "member",
    submission = null,
    stale = false,
    previewDenied = false,
    failDecision = false,
    path,
  } = options;
  const me = PEOPLE[as];
  const organizer = as === "organizer";

  const state = {
    calls: [],
    submission: submission
      ? {
          status: submission,
          submitted_by_id: PEOPLE.member.account_id,
          decided_by_name: submission === "PENDING" ? null : "Professor",
        }
      : null,
  };

  function summary() {
    const item = state.submission;
    return {
      submission_id: SUBMISSION_ID,
      quiz_id: QUIZ_ID,
      quiz_version_id: SUBMITTED_VERSION_ID,
      version_number: 1,
      quiz_title: SUBMITTED_VERSION.title,
      question_count: 1,
      submitted_by_id: item.submitted_by_id,
      submitter_name: "Student",
      status: item.status,
      submitted_at: TIME,
      decided_at: item.status === "PENDING" ? null : TIME,
      decided_by_name: item.decided_by_name,
      is_current_version: !stale,
    };
  }

  function myQuiz() {
    const item = state.submission;
    return {
      quiz_id: QUIZ_ID,
      author_id: PEOPLE.member.account_id,
      class_id: CLASS_ID,
      status: "PUBLISHED",
      title: SUBMITTED_VERSION.title,
      description: null,
      question_count: 1,
      created_at: TIME,
      hosting: {
        can_host: item?.status === "APPROVED",
        reason: item?.status === "APPROVED" ? null : "not_submitted",
        message: null,
      },
      author_name: "Student",
      version_number: 1,
      updated_at: TIME,
      my_access: "OWNER",
      published_version_id: SUBMITTED_VERSION_ID,
      approval_status: item?.status ?? null,
      approval_submission_id: item ? SUBMISSION_ID : null,
      approval_sent_by_me: Boolean(item),
    };
  }

  await page_.route("**/__test_api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path_ = url.pathname.replace("/__test_api", "");
    const method = request.method();
    const body = request.postData() ? request.postDataJSON() : null;
    state.calls.push({ method, path: path_, body });

    const json = (value, status = 200) => route.fulfill({ status, json: value });
    const error = (status, code, message) =>
      json({ error: { code, message } }, status);
    const base = `/classes/${CLASS_ID}`;

    if (method === "GET" && path_ === "/me") {
      return json({ ...me, is_active: true, avatar_key: null });
    }

    if (method === "GET" && path_ === base) {
      return json({
        class_id: CLASS_ID,
        name: "Browser test class",
        current_role: organizer ? "ORGANIZER" : "MEMBER",
        membership_status: "ACTIVE",
        archived_at: null,
        join_code: "TEST1234",
        joining_open: true,
      });
    }

    if (method === "GET" && path_ === `${base}/dashboard`) {
      return json({
        student_count: 1,
        pending_submission_count:
          state.submission?.status === "PENDING" ? 1 : 0,
        approved_quiz_count: state.submission?.status === "APPROVED" ? 1 : 0,
      });
    }

    if (method === "GET" && path_ === `${base}/active-sessions`) {
      return error(404, "not_found", "No live sessions.");
    }

    // Member view: their own quizzes.
    if (method === "GET" && path_ === `${base}/quizzes`) {
      return json({ class_id: CLASS_ID, ...page(organizer ? [] : [myQuiz()]) });
    }

    // Organizer view: the approval queue, filtered by ?status=.
    if (method === "GET" && path_ === `${base}/dashboard/submissions`) {
      const wanted = url.searchParams.get("status");
      const items =
        state.submission && (!wanted || wanted === state.submission.status)
          ? [summary()]
          : [];
      return json(page(items));
    }

    if (
      method === "GET" &&
      path_ === `${base}/dashboard/submissions/${SUBMISSION_ID}/preview`
    ) {
      if (previewDenied || !state.submission) {
        return error(404, "submission_not_found", "Submission not found.");
      }
      return json({ submission: summary(), version: SUBMITTED_VERSION });
    }

    // The quiz itself has moved on to a newer draft. Review screens must
    // keep showing the submitted version, never this one.
    if (method === "GET" && path_ === `/quizzes/${QUIZ_ID}`) {
      return json({
        ...myQuiz(),
        status: "DRAFT",
        revision: 2,
        visibility: "PRIVATE",
        can_edit: !organizer,
        version: {
          ...SUBMITTED_VERSION,
          quiz_version_id: 200,
          version_number: 2,
          published_at: null,
          questions: [question("New draft question", "New draft answer")],
        },
      });
    }

    if (method === "POST" && path_ === `${base}/quiz-submissions`) {
      state.submission = {
        status: "PENDING",
        submitted_by_id: me.account_id,
        decided_by_name: null,
      };
      return json(
        {
          submission_id: SUBMISSION_ID,
          class_id: CLASS_ID,
          quiz_version_id: body.quiz_version_id,
          submitted_by_id: me.account_id,
          status: "PENDING",
          submitted_at: TIME,
          decided_at: null,
          decided_by_id: null,
        },
        201,
      );
    }

    if (path_ === `${base}/quiz-submissions/${SUBMISSION_ID}`) {
      if (method === "PATCH") {
        if (failDecision) {
          return error(
            409,
            "quiz_version_stale",
            "A newer published version of this quiz is available.",
          );
        }
        state.submission.status = body.status;
        state.submission.decided_by_name = "Professor";
        return json({ submission_id: SUBMISSION_ID, status: body.status });
      }
      if (method === "DELETE") {
        state.submission.status = "WITHDRAWN";
        return route.fulfill({ status: 204 });
      }
    }

    return error(500, "unhandled_test_request", `${method} ${path_}`);
  });

  const start =
    path ??
    (organizer
      ? `/app/classes/${CLASS_ID}?view=admin&section=Approvals`
      : `/app/classes/${CLASS_ID}?section=Present`);
  await page_.goto(start);
  return state;
}

export const IDS = { CLASS_ID, SUBMISSION_ID, SUBMITTED_VERSION_ID };
