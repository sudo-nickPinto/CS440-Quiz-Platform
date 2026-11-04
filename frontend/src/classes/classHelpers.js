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
