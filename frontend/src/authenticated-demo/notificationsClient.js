// WebSocket client for the per-account notification socket
// (docs/LIVE_PROTOCOL.md §11). Events are hints: the page refetches over
// HTTP, so a missing or broken socket only means slower updates. Nothing here
// throws or shows an error; failures go to console.debug at most.
// No React here, so it runs the same in the browser and in Node tests.

import { NEEDS_INTERACTION } from "../api";

// Same cadence as the quiz-edit and live sockets; the server drops a socket
// after 120 s of silence, which leaves room for hidden tabs whose timers the
// browser throttles.
export const NOTIFICATIONS_PING_MS = 25_000;
export const NOTIFICATIONS_MAX_BACKOFF_MS = 30_000;

// 4400: we sent something the server doesn't accept (a bug; retrying
// repeats it). 4403: inactive, unknown or unverified account.
const FINAL_CLOSE_CODES = new Set([4400, 4403]);
const UNAUTHORIZED = 4401;

// http://host:8000 -> ws://host:8000/ws/notifications (https -> wss).
export function notificationsSocketUrl(apiBaseUrl) {
  const base = String(apiBaseUrl ?? "").replace(/\/+$/, "").replace(/^http/, "ws");
  return `${base}/ws/notifications`;
}

// 1 s, 2 s, 4 s ... capped at 30 s.
export function notificationsBackoff(attempt) {
  return Math.min(1000 * 2 ** attempt, NOTIFICATIONS_MAX_BACKOFF_MS);
}

/**
 * Opens the socket and keeps it open until close().
 *
 *   getToken({ freshToken })  resolves to an Auth0 access token
 *   onEvent(message)          every server message except ready and pong
 *   onReady({ reconnected })  each time the server says notifications_ready;
 *                             reconnected is true after an earlier ready, so
 *                             the page may have missed events in between
 *   onStatus(status)          "connecting" | "open" | "reconnecting" |
 *                             "stopped" | "closed"
 */
export function createNotificationsClient({
  url,
  getToken,
  onEvent = () => {},
  onReady = () => {},
  onStatus = () => {},
  WebSocketImpl = globalThis.WebSocket,
  timers = globalThis,
  pingIntervalMs = NOTIFICATIONS_PING_MS,
  log = (...args) => console.debug("[notifications]", ...args),
}) {
  let socket = null;
  let stopped = false;
  let attempt = 0;
  let retriedAuth = false;
  let everReady = false;
  let pingTimer = null;
  let retryTimer = null;

  function safely(callback, ...args) {
    try {
      callback(...args);
    } catch (error) {
      log("handler failed", error);
    }
  }

  function stopPing() {
    if (pingTimer !== null) timers.clearInterval(pingTimer);
    pingTimer = null;
  }

  function stop(reason) {
    stopped = true;
    stopPing();
    log("stopped:", reason);
    safely(onStatus, "stopped");
  }

  function retryLater() {
    if (stopped) return;
    const delay = notificationsBackoff(attempt);
    attempt += 1;
    safely(onStatus, "reconnecting");
    retryTimer = timers.setTimeout(() => {
      retryTimer = null;
      void connect();
    }, delay);
  }

  async function connect({ freshToken = false } = {}) {
    if (stopped) return;
    if (typeof WebSocketImpl !== "function") {
      stop("WebSocket is not available");
      return;
    }

    let token;
    try {
      token = await getToken({ freshToken });
    } catch (error) {
      if (stopped) return;
      // Signed out or needs an interactive sign-in: nothing to retry.
      if (NEEDS_INTERACTION.includes(error?.error)) {
        stop(`no token (${error.error})`);
        return;
      }
      log("could not get a token", error);
      retryLater();
      return;
    }
    if (stopped) return;

    let current;
    try {
      current = new WebSocketImpl(url);
    } catch (error) {
      // A malformed URL won't get better by retrying.
      stop(`could not open ${url}: ${error?.message ?? error}`);
      return;
    }
    socket = current;

    current.onopen = () => {
      try {
        current.send(JSON.stringify({ type: "auth", token }));
      } catch (error) {
        log("could not send auth", error);
      }
    };

    current.onmessage = (event) => {
      let message;
      try {
        message = JSON.parse(event.data);
      } catch {
        return;
      }
      if (!message || typeof message.type !== "string") return;
      if (message.type === "pong") return;
      if (message.type === "notifications_ready") {
        const reconnected = everReady;
        everReady = true;
        attempt = 0;
        retriedAuth = false;
        stopPing();
        pingTimer = timers.setInterval(() => {
          try {
            current.send(JSON.stringify({ type: "ping" }));
          } catch (error) {
            log("ping failed", error);
          }
        }, pingIntervalMs);
        safely(onStatus, "open");
        safely(onReady, { reconnected });
        return;
      }
      safely(onEvent, message);
    };

    current.onerror = () => {
      // The close event that follows decides what to do.
    };

    current.onclose = (event) => {
      if (socket !== current) return; // an older socket we already replaced
      socket = null;
      stopPing();
      if (stopped) return;

      const code = event?.code;
      if (FINAL_CLOSE_CODES.has(code)) {
        stop(`closed ${code} ${event?.reason ?? ""}`.trim());
        return;
      }
      if (code === UNAUTHORIZED) {
        // Expired or refused token: one immediate retry with a fresh one,
        // then back off, and give up if that one is refused too.
        if (retriedAuth) {
          stop("token refused twice (4401)");
          return;
        }
        retriedAuth = true;
        safely(onStatus, "reconnecting");
        void connect({ freshToken: true });
        return;
      }
      // 1001 idle timeout or server restart, 1011, 1006 network drop.
      retryLater();
    };
  }

  safely(onStatus, "connecting");
  void connect();

  return {
    close() {
      if (stopped && socket === null && retryTimer === null) return;
      stopped = true;
      stopPing();
      if (retryTimer !== null) timers.clearTimeout(retryTimer);
      retryTimer = null;
      const current = socket;
      socket = null;
      try {
        current?.close(1000, "client_closed");
      } catch {
        // already closing
      }
      safely(onStatus, "closed");
    },
  };
}
