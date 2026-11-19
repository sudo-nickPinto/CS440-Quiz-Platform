import { createContext, useContext, useEffect, useRef } from "react";

// Server pushes for the signed-in account (docs/LIVE_PROTOCOL.md §11), shared
// by every page through NotificationsProvider. Outside a provider (unit
// tests, the sign-in screens) the hooks below do nothing.
export const NotificationsContext = createContext(null);

// Focus changes in quick succession refetch at most once in this window.
export const CATCH_UP_THROTTLE_MS = 10_000;

// A tiny event bus the provider feeds from the socket.
//   subscribe(type, handler)  one event type, or "*" for every event;
//                             returns an unsubscribe function
//   onReconnect(handler)      runs when the socket is ready again after a
//                             drop, so pages can refetch what they missed
//   onCatchUp(handler)        runs when pages may be out of date: after a
//                             reconnect, or when the tab comes back
//   catchUp({ force })        runs the onCatchUp handlers, at most once per
//                             CATCH_UP_THROTTLE_MS unless forced
export function createNotificationsBus() {
  const handlers = new Map();
  const reconnectHandlers = new Set();
  const catchUpHandlers = new Set();
  // The app was just loaded; don't refetch on the first focus.
  let lastCatchUp = Date.now();

  function run(handler, value) {
    try {
      handler(value);
    } catch (error) {
      console.debug("[notifications] handler failed", error);
    }
  }

  return {
    subscribe(type, handler) {
      if (!handlers.has(type)) handlers.set(type, new Set());
      handlers.get(type).add(handler);
      return () => handlers.get(type)?.delete(handler);
    },
    onReconnect(handler) {
      reconnectHandlers.add(handler);
      return () => reconnectHandlers.delete(handler);
    },
    emit(event) {
      for (const handler of [...(handlers.get(event?.type) ?? [])]) run(handler, event);
      for (const handler of [...(handlers.get("*") ?? [])]) run(handler, event);
    },
    emitReconnect() {
      for (const handler of [...reconnectHandlers]) run(handler);
    },
    onCatchUp(handler) {
      catchUpHandlers.add(handler);
      return () => catchUpHandlers.delete(handler);
    },
    catchUp({ force = false } = {}) {
      const now = Date.now();
      if (!force && now - lastCatchUp < CATCH_UP_THROTTLE_MS) return;
      lastCatchUp = now;
      for (const handler of [...catchUpHandlers]) run(handler);
    },
  };
}

// Keeps the newest handler without resubscribing on every render.
function useLatest(handler) {
  const latest = useRef(handler);
  useEffect(() => {
    latest.current = handler;
  });
  return latest;
}

/**
 * Calls handler(event) for each pushed event of the given type (a string,
 * an array of strings, or "*" for all). The handler may change between
 * renders; only a change of type resubscribes.
 *
 *   useNotifications("session_live", (event) => ...)
 */
export function useNotifications(types, handler) {
  const bus = useContext(NotificationsContext);
  const latest = useLatest(handler);
  const key = [types].flat().filter(Boolean).join(",");

  useEffect(() => {
    if (!bus || !key) return undefined;
    const unsubscribers = key
      .split(",")
      .map((type) => bus.subscribe(type, (event) => latest.current?.(event)));
    return () => unsubscribers.forEach((unsubscribe) => unsubscribe());
  }, [bus, key, latest]);
}

// Calls handler() each time the socket is ready again after a disconnect
// (not on the first connect), since events sent meanwhile are not replayed.
export function useNotificationsReconnect(handler) {
  const bus = useContext(NotificationsContext);
  const latest = useLatest(handler);

  useEffect(() => {
    if (!bus) return undefined;
    return bus.onReconnect(() => latest.current?.());
  }, [bus, latest]);
}

/**
 * Calls handler() when the page may be out of date: the notification socket
 * reconnected, or the window regained focus / the tab became visible again.
 * NotificationsProvider owns the one focus/visibility listener and throttles
 * it for every page at once, so a tab switch refetches each resource at most
 * once. Outside a provider this does nothing.
 */
export function useCatchUp(handler) {
  const bus = useContext(NotificationsContext);
  const latest = useLatest(handler);

  useEffect(() => {
    if (!bus) return undefined;
    return bus.onCatchUp(() => latest.current?.());
  }, [bus, latest]);
}
