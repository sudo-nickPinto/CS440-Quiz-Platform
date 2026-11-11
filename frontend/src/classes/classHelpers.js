// The big banner label from classes-main.html ("CS 440", "ALGO"). Classes
// have no separate course code, so take a leading "CS 440"-style code from
// the name, or else its first word.
export function shortName(name) {
  const course = name.match(/^\s*([A-Za-z]{2,5})[\s-]?(\d{2,4}[A-Za-z]?)\b/);
  if (course) return `${course[1]} ${course[2]}`.toUpperCase();
  return name.trim().split(/\s+/)[0].slice(0, 8).toUpperCase();
}

export function copyText(text) {
  return navigator.clipboard?.writeText(text).catch(() => {});
}

// Sort choices for a class's "My quizzes" list (GET /classes/{id}/quizzes).
export const MY_QUIZ_SORTS = {
  recent: { label: "Recently edited", sort: "updated_at", order: "desc" },
  newest: { label: "Newest", sort: "created_at", order: "desc" },
  title: { label: "Title A–Z", sort: "title", order: "asc" },
};

export function myQuizzesPath(classId, page = 1, sortKey = "recent", pageSize = 25) {
  const choice = MY_QUIZ_SORTS[sortKey] ?? MY_QUIZ_SORTS.recent;
  return (
    `/classes/${classId}/quizzes?mine=true&page=${page}&page_size=${pageSize}` +
    `&sort=${choice.sort}&order=${choice.order}`
  );
}

export function quizAccessLabel(access) {
  return access === "OWNER" ? "Owner" : access === "EDITOR" ? "Editor" : "—";
}

export function quizStatusLabel(status) {
  return (
    { DRAFT: "Draft", PUBLISHED: "Published", ARCHIVED: "Archived" }[status] ??
    "—"
  );
}

// Sort choices for the approval queue (GET /classes/{id}/dashboard/submissions).
export const SUBMISSION_SORTS = {
  newest: { label: "Newest first", sort: "submitted_at", order: "desc" },
  oldest: { label: "Oldest first", sort: "submitted_at", order: "asc" },
  title: { label: "Quiz A–Z", sort: "title", order: "asc" },
  submitter: { label: "Submitter A–Z", sort: "submitter", order: "asc" },
};

export const SUBMISSION_FILTERS = {
  PENDING: "Pending",
  APPROVED: "Approved",
  REJECTED: "Rejected",
  WITHDRAWN: "Withdrawn",
  "": "All",
};

// The exact submitted version (V3 Task 6), or null for a bad address.
export function submissionPreviewPath(classId, submissionId) {
  const valid = (value) => /^[1-9]\d*$/.test(String(value ?? ""));
  if (!valid(classId) || !valid(submissionId)) return null;
  return `/classes/${classId}/dashboard/submissions/${submissionId}/preview`;
}

export function submissionsPath(
  classId,
  page = 1,
  sortKey = "newest",
  status = "",
  pageSize = 25,
) {
  const choice = SUBMISSION_SORTS[sortKey] ?? SUBMISSION_SORTS.newest;
  const filter = status in SUBMISSION_FILTERS && status ? `&status=${status}` : "";
  return (
    `/classes/${classId}/dashboard/submissions?page=${page}&page_size=${pageSize}` +
    `&sort=${choice.sort}&order=${choice.order}${filter}`
  );
}

// Sort choices for the approved quizzes a class can host.
export const APPROVED_SORTS = {
  recent: { label: "Recently approved", sort: "approved_at", order: "desc" },
  title: { label: "Title A–Z", sort: "title", order: "asc" },
};

export function approvedQuizzesPath(classId, page = 1, sortKey = "recent", pageSize = 24) {
  const choice = APPROVED_SORTS[sortKey] ?? APPROVED_SORTS.recent;
  return (
    `/classes/${classId}/dashboard/approved-quizzes?page=${page}&page_size=${pageSize}` +
    `&sort=${choice.sort}&order=${choice.order}`
  );
}

export function approvalLabel(status) {
  return (
    {
      PENDING: "Waiting for approval",
      APPROVED: "Approved",
      REJECTED: "Rejected",
      WITHDRAWN: "Withdrawn",
    }[status] ?? "Not submitted"
  );
}

// A quiz from "My quizzes" can be sent for approval once it has a published
// version that isn't already pending or approved. Rejected and withdrawn
// versions may be sent again.
export function canSubmitForApproval(quiz) {
  return (
    quiz.status === "PUBLISHED" &&
    quiz.my_access !== null &&
    quiz.my_access !== undefined &&
    Number.isSafeInteger(quiz.published_version_id) &&
    quiz.approval_status !== "PENDING" &&
    quiz.approval_status !== "APPROVED"
  );
}

// Admin view tabs, left to right. "Students" is the roster (students with
// their scores, plus co-organizers and invites); "Presentations" shows class
// history by session or by quiz. Settings is a dialog opened from the class
// header, not a tab.
export const ADMIN_SECTIONS = ["Students", "Presentations", "Approvals"];
export const HISTORY_VIEWS = { sessions: "By session", quizzes: "By quiz" };

// Maps a ?section= value onto the admin tabs, including the names of the
// tabs that were merged or renamed (Quizzes, Members, Settings).
export function resolveAdminSection(requested) {
  if (requested === "Quizzes") {
    return { section: "Presentations", historyView: "quizzes", settingsOpen: false };
  }
  if (requested === "Members") {
    return { section: "Students", historyView: "sessions", settingsOpen: false };
  }
  if (requested === "Settings") {
    return { section: "Students", historyView: "sessions", settingsOpen: true };
  }
  return {
    section: ADMIN_SECTIONS.includes(requested) ? requested : "Students",
    historyView: "sessions",
    settingsOpen: false,
  };
}

// Sort choices for the merged Members table (sorted in the browser).
export const MEMBER_SORTS = {
  name: "Name A–Z",
  average: "Best average",
  role: "Organizers first",
};

function memberName(member) {
  return (member.display_name || member.email || "").toLowerCase();
}

// Joins the member list with the organizer-only student scores. Organizers
// have no scores, so their `stats` is null.
export function membersWithStats(members, statsById, sortKey = "name") {
  const rows = members.map((member) => ({
    ...member,
    stats: statsById?.get(Number(member.account_id)) ?? null,
  }));
  const byName = (a, b) =>
    memberName(a).localeCompare(memberName(b)) ||
    Number(a.account_id) - Number(b.account_id);
  const average = (row) => row.stats?.average_score ?? -1;
  const organizerFirst = (row) => (row.role === "ORGANIZER" ? 0 : 1);

  const compare = {
    name: byName,
    average: (a, b) => average(b) - average(a) || byName(a, b),
    role: (a, b) => organizerFirst(a) - organizerFirst(b) || byName(a, b),
  }[sortKey] ?? byName;

  return rows.sort(compare);
}
