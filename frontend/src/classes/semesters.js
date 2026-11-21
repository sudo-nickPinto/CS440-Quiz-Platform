// Semester labels such as "Fall 2026". The server only accepts Spring,
// Summer or Fall and a year, so the forms only offer those.

const LABEL = /^(spring|summer|fall)\s+(\d{4})$/i;
const TERM_ORDER = { spring: 0, summer: 1, fall: 2 };

function parse(label) {
  const match = LABEL.exec(String(label ?? "").trim());
  if (!match) return null;
  return { term: match[1].toLowerCase(), year: Number(match[2]) };
}

export function semesterFor(date = new Date()) {
  const month = date.getMonth();
  const term = month <= 4 ? "Spring" : month <= 6 ? "Summer" : "Fall";
  return `${term} ${date.getFullYear()}`;
}

// The regular semester after `label`: Fall 2026 -> Spring 2027, and Spring
// or Summer 2027 -> Fall 2027. A label in another format counts from today.
export function nextSemester(label, today = new Date()) {
  const parsed = parse(label);
  if (!parsed) return nextSemester(semesterFor(today));
  return parsed.term === "fall"
    ? `Spring ${parsed.year + 1}`
    : `Fall ${parsed.year}`;
}

// The regular semester before `label`: Spring 2027 -> Fall 2026, and Fall
// or Summer 2026 -> Spring 2026.
export function previousSemester(label, today = new Date()) {
  const parsed = parse(label);
  if (!parsed) return previousSemester(semesterFor(today));
  return parsed.term === "spring"
    ? `Fall ${parsed.year - 1}`
    : `Spring ${parsed.year}`;
}

// Oldest first. Anything that isn't a semester label sorts first.
export function compareSemesters(a, b) {
  const left = parse(a);
  const right = parse(b);
  if (!left || !right) return Number(Boolean(left)) - Number(Boolean(right));
  return (
    left.year - right.year || TERM_ORDER[left.term] - TERM_ORDER[right.term]
  );
}

// The choices for a semester picker: `before` semesters before `from`
// (today's semester when `from` isn't a semester), `from` itself, and
// `after` semesters after it.
export function semesterChoices({
  from,
  before = 1,
  after = 3,
  today = new Date(),
} = {}) {
  const start = parse(from) ? from.trim() : semesterFor(today);
  const earlier = [];
  let label = start;
  for (let i = 0; i < before; i += 1) {
    label = previousSemester(label);
    earlier.unshift(label);
  }
  const later = [];
  label = start;
  for (let i = 0; i < after; i += 1) {
    label = nextSemester(label);
    later.push(label);
  }
  return [...earlier, start, ...later];
}

// What "Start a new semester" offers: the next few semesters after the
// newest one the course has, leaving out any it already has.
export function newSemesterChoices(existing, today = new Date()) {
  const labels = existing.filter(Boolean);
  const newest = [...labels].sort(compareSemesters).at(-1);
  const taken = new Set(labels.map((label) => label.toLowerCase()));
  const from = newest ? nextSemester(newest) : semesterFor(today);
  return semesterChoices({ from, before: 0, after: 3, today }).filter(
    (label) => !taken.has(label.toLowerCase()),
  );
}

// "CS 440 · Fall 2026", or just the name for classes with no semester.
export function classLabel(item) {
  return item.semester ? `${item.name} · ${item.semester}` : item.name;
}

// One card per course on the Classes page. Semesters of a course you
// organize share a parent class; the card shows the newest active semester
// (or the newest, when all are archived) and opens it. Classes you don't
// organize stay one card each, since only organizers switch semesters.
export function groupCourses(classes) {
  const groups = new Map();
  const cards = [];
  for (const item of classes) {
    if (!item.canManage) {
      cards.push(item);
      continue;
    }
    const root = item.parentClassId ?? item.id;
    if (!groups.has(root)) {
      groups.set(root, []);
      cards.push(groups.get(root));
    }
    groups.get(root).push(item);
  }
  return cards.map((card) => {
    if (!Array.isArray(card)) return card;
    const newestFirst = [...card].sort(
      (a, b) => compareSemesters(b.semester, a.semester) || b.id - a.id,
    );
    const shown = newestFirst.find((item) => !item.archived) ?? newestFirst[0];
    return { ...shown, semesterCount: card.length };
  });
}
