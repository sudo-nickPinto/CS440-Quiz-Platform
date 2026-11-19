// Semester labels such as "Fall 2026". A class's semester is free text on
// the server; these helpers only suggest values for the forms.

export function semesterFor(date = new Date()) {
  const month = date.getMonth();
  const term = month <= 4 ? "Spring" : month <= 6 ? "Summer" : "Fall";
  return `${term} ${date.getFullYear()}`;
}

// The regular semester after `label`: Fall 2026 -> Spring 2027, and Spring
// or Summer 2027 -> Fall 2027. A label in another format counts from today.
export function nextSemester(label, today = new Date()) {
  const match = /^(spring|summer|fall)\s+(\d{4})$/i.exec(String(label ?? "").trim());
  if (!match) return nextSemester(semesterFor(today));
  const year = Number(match[2]);
  return match[1].toLowerCase() === "fall" ? `Spring ${year + 1}` : `Fall ${year}`;
}

// This semester and the next two, for the semester box's suggestions.
export function semesterOptions(today = new Date()) {
  const current = semesterFor(today);
  const next = nextSemester(current);
  return [current, next, nextSemester(next)];
}

// "CS 440 · Fall 2026", or just the name for classes with no semester.
export function classLabel(item) {
  return item.semester ? `${item.name} · ${item.semester}` : item.name;
}
