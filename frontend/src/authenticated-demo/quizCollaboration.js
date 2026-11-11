export const QUIZ_EDIT_PING_MS = 25_000;
const FINAL_CLOSE_CODES = new Set([4400, 4401, 4403, 4404]);

export function quizEditSocketUrl(apiBaseUrl, quizId) {
  const base = apiBaseUrl.replace(/\/+$/, "").replace(/^http/, "ws");
  return `${base}/ws/quizzes/${quizId}`;
}

export function createQuizEditClient({
  url,
  getToken,
  onMessage = () => {},
  onStatus = () => {},
  WebSocketImpl = globalThis.WebSocket,
  timers = globalThis,
  pingIntervalMs = QUIZ_EDIT_PING_MS,
}) {
  let socket = null;
  let stopped = false;
  let retryTimer = null;
  let pingTimer = null;
  let attempts = 0;

  function clearTimers() {
    if (retryTimer !== null) timers.clearTimeout(retryTimer);
    if (pingTimer !== null) timers.clearInterval(pingTimer);
    retryTimer = null;
    pingTimer = null;
  }

  async function connect() {
    if (stopped) return;
    onStatus(attempts ? "reconnecting" : "connecting");
    let token;
    try {
      token = await getToken();
    } catch (error) {
      onStatus("unauthorized", error);
      return;
    }
    if (stopped) return;

    const current = new WebSocketImpl(url);
    socket = current;
    current.onopen = () => {
      current.send(JSON.stringify({ type: "auth", token }));
    };
    current.onmessage = (event) => {
      let message;
      try {
        message = JSON.parse(event.data);
      } catch {
        return;
      }
      if (message.type === "quiz_editor_state") {
        attempts = 0;
        onStatus("open");
        if (pingTimer !== null) timers.clearInterval(pingTimer);
        pingTimer = timers.setInterval(() => {
          current.send(JSON.stringify({ type: "ping" }));
        }, pingIntervalMs);
      }
      if (message.type !== "pong") onMessage(message);
    };
    current.onclose = (event) => {
      if (socket !== current) return;
      socket = null;
      if (pingTimer !== null) timers.clearInterval(pingTimer);
      pingTimer = null;
      if (stopped) return;
      if (FINAL_CLOSE_CODES.has(event.code)) {
        stopped = true;
        onStatus("failed", event);
        return;
      }
      const delay = Math.min(1000 * 2 ** attempts, 30_000);
      attempts += 1;
      onStatus("reconnecting", event);
      retryTimer = timers.setTimeout(connect, delay);
    };
  }

  void connect();
  return {
    close() {
      stopped = true;
      clearTimers();
      socket?.close(1000, "editor_closed");
      socket = null;
      onStatus("closed");
    },
  };
}
