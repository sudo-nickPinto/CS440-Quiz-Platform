// Kept in its own file (not classHelpers.js) so this branch doesn't edit the
// same lines as #108, which also changes classHelpers.js.

// Where "back" goes once a quiz or session is done: its class page, or the
// class list for old pre-V3 records with no class. The global dashboard is
// gone, so everything lives under a class.
export function classPagePath(classId) {
  const id = Number(classId);
  return Number.isSafeInteger(id) && id > 0 ? `/app/classes/${id}` : "/app/classes";
}
