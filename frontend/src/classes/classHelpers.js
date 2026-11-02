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
