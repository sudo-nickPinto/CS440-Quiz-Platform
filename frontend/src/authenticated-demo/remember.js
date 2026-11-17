import { useEffect, useState } from "react";

// Remembers small bits of page state (which tab, sort, filter, page, search)
// for this browser tab, so leaving a page and coming back lands where you
// were. sessionStorage is per tab and clears when the tab closes; if it is
// blocked, pages fall back to their defaults.
const PREFIX = "qb:remember:";

export function readRemembered(key) {
  if (!key) return undefined;
  try {
    const raw = window.sessionStorage.getItem(PREFIX + key);
    return raw === null ? undefined : JSON.parse(raw);
  } catch {
    return undefined;
  }
}

export function writeRemembered(key, value) {
  if (!key) return;
  try {
    window.sessionStorage.setItem(PREFIX + key, JSON.stringify(value));
  } catch {
    // Storage full or blocked: nothing to remember.
  }
}

// Which value a page starts with: an explicit one (say from a ?section= link)
// wins, then the remembered one if it is still valid, then the default.
export function pickStart(saved, fallback, { override, isValid } = {}) {
  if (override !== undefined && override !== null) return override;
  if (saved !== undefined && (!isValid || isValid(saved))) return saved;
  return typeof fallback === "function" ? fallback() : fallback;
}

// useState that is remembered under `key` (no key: plain useState).
export function useRemembered(key, fallback, options) {
  const [value, setValue] = useState(() =>
    pickStart(readRemembered(key), fallback, options),
  );

  useEffect(() => {
    writeRemembered(key, value);
  }, [key, value]);

  return [value, setValue];
}

// Browser Back/Forward returns to the scroll position the page was left at.
// Positions are stored per history entry (location.key).
const SCROLL_PREFIX = "scroll:";

export function savedScroll(locationKey) {
  return readRemembered(SCROLL_PREFIX + locationKey) ?? 0;
}

export function saveScroll(locationKey) {
  writeRemembered(SCROLL_PREFIX + locationKey, Math.round(window.scrollY));
}

// Content loads after the route renders, so keep trying for a moment until
// the page is tall enough to reach the saved spot.
export function restoreScroll(target) {
  if (!target) {
    window.scrollTo(0, 0);
    return () => {};
  }
  let frame = 0;
  let tries = 0;
  // Stop as soon as the person scrolls on their own.
  const stop = () => {
    cancelAnimationFrame(frame);
    for (const type of USER_SCROLL) window.removeEventListener(type, stop);
  };
  const attempt = () => {
    const room = document.documentElement.scrollHeight - window.innerHeight;
    window.scrollTo(0, Math.min(target, room));
    if (room < target && tries++ < 90) frame = requestAnimationFrame(attempt);
    else stop();
  };
  for (const type of USER_SCROLL) {
    window.addEventListener(type, stop, { passive: true });
  }
  attempt();
  return stop;
}

const USER_SCROLL = ["wheel", "touchstart", "keydown", "pointerdown"];
