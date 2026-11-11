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

// Admin view tabs, left to right. "Students" is the roster (students with
// their scores, plus co-organizers); "Presentations" shows class history by
// session or by quiz. Members are added from the header's "+ Add member".
export const ADMIN_SECTIONS = ["Students", "Presentations", "Approvals"];
export const HISTORY_VIEWS = { sessions: "By session", quizzes: "By quiz" };

// Maps a ?section= value onto the admin tabs, including the names of the
// tabs that were merged or removed (Quizzes, Members, Settings).
export function resolveAdminSection(requested) {
  if (requested === "Quizzes") {
    return { section: "Presentations", historyView: "quizzes" };
  }
  return {
    section: ADMIN_SECTIONS.includes(requested) ? requested : "Students",
    historyView: "sessions",
  };
}

// Member (User view) tabs. "Present" is the caller's own quizzes with their
// approval state; "Participate" is the sessions they played. Old links to
// "My quizzes" land on Present.
export const USER_SECTIONS = ["Present", "Participate"];

export function resolveUserSection(requested) {
  return USER_SECTIONS.includes(requested) ? requested : "Present";
}

// The lead block on a Present row. Members only see Draft or Approved:
// publishing (freezing a version) happens inside "Send for approval". A quiz
// edited after approval is a Draft again until the new version is approved.
export function presentStatus(quiz) {
  if (quiz.status === "ARCHIVED") return { key: "archived", label: "Archived" };
  if (quiz.status === "PUBLISHED" && quiz.approval_status === "APPROVED") {
    return { key: "approved", label: "Approved" };
  }
  return { key: "draft", label: "Draft" };
}

// The one approval button on a Present row and the short note under it.
//   send      Send for approval / Send again (orange)
//   withdraw  Withdraw request (while waiting, for whoever sent it)
//   waiting   Waiting for approval (sent by a co-editor; not clickable)
//   approved  ✓ Approved (blue; not clickable)
// A draft on top of the published version has to be published first, and
// only the owner can publish, so co-editors can't send it.
export function approvalButton(quiz) {
  if (quiz.status === "ARCHIVED" || !quiz.my_access) return null;
  const edited = quiz.status === "DRAFT" && Boolean(quiz.published_version_id);
  const status = quiz.approval_status;

  if (status === "APPROVED" && quiz.status === "PUBLISHED") {
    return { kind: "approved", label: "✓ Approved", disabled: true, note: null };
  }
  if (status === "PENDING") {
    const note = edited ? "Edited since request" : null;
    return quiz.approval_sent_by_me
      ? { kind: "withdraw", label: "Withdraw request", disabled: false, note }
      : { kind: "waiting", label: "Waiting for approval", disabled: true, note };
  }

  const needsPublish = quiz.status === "DRAFT";
  const ownerOnly = needsPublish && quiz.my_access !== "OWNER";
  const note =
    status === "APPROVED"
      ? "Edited since approval"
      : status === "REJECTED"
        ? "Rejected"
        : null;
  return {
    kind: "send",
    label: status === "REJECTED" ? "Send again" : "Send for approval",
    disabled: ownerOnly,
    title: ownerOnly ? "Only the quiz owner can send a new version" : undefined,
    note,
  };
}

// Sends the quiz's current content for approval. If there are edits since
// the last frozen version, publish them first (owner only), then submit
// that version.
export async function sendForApproval(api, classId, quiz) {
  let versionId = quiz.status === "PUBLISHED" ? quiz.published_version_id : null;
  if (!versionId) {
    const current = await api(`/quizzes/${quiz.quiz_id}`);
    const published = await api(
      `/classes/${classId}/quizzes/${quiz.quiz_id}/publish`,
      {
        method: "POST",
        body: JSON.stringify({ expected_revision: current.revision }),
      },
    );
    versionId = published.version.quiz_version_id;
  }
  return api(`/classes/${classId}/quiz-submissions`, {
    method: "POST",
    body: JSON.stringify({ quiz_version_id: versionId }),
  });
}

// Class rank by average points, best first. Students who never played have
// no rank; equal averages share one ("1, 1, 3").
export function studentRanks(rows) {
  const ranked = rows
    .filter((row) => row.role !== "ORGANIZER" && row.stats?.average_score != null)
    .sort((a, b) => b.stats.average_score - a.stats.average_score);
  const ranks = new Map();
  ranked.forEach((row, index) => {
    const previous = ranked[index - 1];
    const rank =
      previous && previous.stats.average_score === row.stats.average_score
        ? ranks.get(Number(previous.account_id))
        : index + 1;
    ranks.set(Number(row.account_id), rank);
  });
  return ranks;
}

// Colors a score chip: "miss" when absent, "hi" at or above that
// presentation's class average, otherwise "lo".
export function scoreMark(score, average) {
  if (score === null || score === undefined) return "miss";
  if (average === null || average === undefined) return "hi";
  return score >= average ? "hi" : "lo";
}

export function initials(name) {
  const words = String(name ?? "")
    .replace(/@.*/, "")
    .split(/[\s._-]+/)
    .filter(Boolean);
  return (words.length > 1 ? words[0][0] + words[1][0] : (words[0] ?? "?").slice(0, 2))
    .toUpperCase();
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
