// Helpers for the Faculty access page (issue #116). Faculty status is the
// account's ADMIN role: it lets someone create classes and be made a class
// organizer, but never opens classes they don't organize.

const DATE = new Intl.DateTimeFormat(undefined, {
  month: "short",
  day: "numeric",
  year: "numeric",
});

const DATE_TIME = new Intl.DateTimeFormat(undefined, {
  month: "short",
  day: "numeric",
  year: "numeric",
  hour: "numeric",
  minute: "2-digit",
});

export function isFaculty(account) {
  return account?.is_active === true && account?.role === "ADMIN";
}

// A light check so obvious typos get caught before asking the server; the
// server still decides whether an account with that email exists.
export function looksLikeEmail(value) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(value ?? "").trim());
}

export function grantedLabel(member) {
  if (!member?.granted_at) return "Set up by a maintainer";
  const date = DATE.format(new Date(member.granted_at));
  return member.granted_by_name
    ? `Added by ${member.granted_by_name} · ${date}`
    : `Added ${date}`;
}

export function historySentence(item) {
  return item.action === "REVOKED"
    ? `${item.actor_name} removed faculty access from ${item.account_name}`
    : `${item.actor_name} gave faculty access to ${item.account_name}`;
}

export function historyTime(item) {
  return DATE_TIME.format(new Date(item.occurred_at));
}

// Me first, then everyone else in the order the server sent (by name).
export function orderFaculty(faculty) {
  if (!Array.isArray(faculty)) return [];
  return [...faculty].sort((a, b) => Number(b.is_me) - Number(a.is_me));
}
