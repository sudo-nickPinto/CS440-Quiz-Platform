// Helpers for the Trash page and the "type to confirm" dialogs.

const KIND_LABELS = { class: "Class", quiz: "Quiz", session: "Session" };

// Typing the class name before a destructive action. Case and extra
// spaces don't matter.
export function matchesTyped(typed, expected) {
  const clean = (value) => value.trim().replace(/\s+/g, " ").toLowerCase();
  return clean(typed) === clean(expected);
}

// Gone within this many days: the card says so in red.
const SOON_DAYS = 3;

function daysLeft(item) {
  const days = item.days_left;
  if (days == null) return "";
  return days <= 1 ? "Deleted tomorrow" : `${days} days left`;
}

// Everything in GET /trash as one list of cards, classes first.
export function trashRows(data) {
  if (!data) return [];
  const row = (kind, id, fields) => ({
    key: `${kind}:${id}`,
    kind,
    kindLabel: KIND_LABELS[kind],
    id,
    soon: fields.daysLeft != null && fields.daysLeft <= SOON_DAYS,
    ...fields,
  });
  return [
    ...data.classes.map((item) =>
      row("class", item.class_id, {
        title: item.name,
        name: item.name,
        detail: item.semester,
        days: daysLeft(item),
        daysLeft: item.days_left,
      }),
    ),
    ...data.quizzes.map((item) =>
      row("quiz", item.quiz_id, {
        title: item.title,
        detail: item.class_name,
        days: daysLeft(item),
        daysLeft: item.days_left,
        blocked: item.class_in_trash,
      }),
    ),
    ...data.sessions.map((item) =>
      row("session", item.session_id, {
        title: `${item.quiz_title} · Session #${item.session_id}`,
        detail: item.class_name,
        days: daysLeft(item),
        daysLeft: item.days_left,
        blocked: item.class_in_trash,
      }),
    ),
  ];
}

// The request body for POST /trash/restore and /trash/purge.
export function trashSelection(rows) {
  const body = { class_ids: [], quiz_ids: [], session_ids: [] };
  for (const row of rows) body[`${row.kind}_ids`].push(row.id);
  return body;
}
