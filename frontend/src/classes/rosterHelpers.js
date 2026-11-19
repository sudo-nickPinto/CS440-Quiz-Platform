// Labels and summaries for the roster import, join requests and the
// "+ Add student" suggestions (backend: app/services/class_roster.py).

// What happened to one roster row, in the order the summary lists them.
export const ROSTER_OUTCOMES = {
  added: { label: "Added", tone: "good" },
  approved: { label: "Request approved", tone: "good" },
  expected: { label: "No account yet", tone: "wait" },
  name_match: { label: "Same name, check email", tone: "warn" },
  already_in_class: { label: "Already in class", tone: "none" },
  ambiguous: { label: "Same name as others", tone: "warn" },
  removed: { label: "Removed earlier", tone: "warn" },
  skipped: { label: "Skipped", tone: "warn" },
};

export function outcomeLabel(outcome) {
  return ROSTER_OUTCOMES[outcome]?.label ?? outcome;
}

// "3 invited · 1 no account yet · 1 skipped", in ROSTER_OUTCOMES order.
export function rosterSummary(counts) {
  return Object.keys(ROSTER_OUTCOMES)
    .filter((key) => counts?.[key] > 0)
    .map((key) => `${counts[key]} ${ROSTER_OUTCOMES[key].label.toLowerCase()}`)
    .join(" · ");
}

// True when importing would change anything (and so is worth a button).
export function rosterHasChanges(counts) {
  return ["added", "approved", "expected", "ambiguous", "name_match"].some(
    (key) => counts?.[key] > 0,
  );
}

// "Rivera, Maya" for a roster row; the registrar's file is Last,First.
export function rosterName(row) {
  const last = row.last_name ?? "";
  const first = row.first_name ?? "";
  if (last && first) return `${last}, ${first}`;
  return last || first || "—";
}

// What a suggestion's existing class membership means for "Add". A
// pending invitation from before can still be added (it becomes membership).
export function suggestionStatus(status) {
  switch (status) {
    case "ACTIVE":
      return { label: "Already a student", canAdd: false };
    case "INVITED":
      return { label: "Invited", canAdd: true };
    case "REQUESTED":
      return { label: "Waiting for approval", canAdd: false };
    case "REMOVED":
      return { label: "Removed earlier", canAdd: true };
    default:
      return { label: null, canAdd: true };
  }
}

// Only ask the server once the search could match something.
export function suggestionQuery(text) {
  const query = String(text ?? "")
    .trim()
    .replace(/\s+/g, " ");
  return query.length >= 2 ? query : "";
}

// Roster files: CSV or Excel. Older .xls files aren't supported.
export const ROSTER_ACCEPT =
  ".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

export function rosterContentType(file) {
  return /\.xlsx$/i.test(file?.name ?? "")
    ? "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    : "text/csv";
}
