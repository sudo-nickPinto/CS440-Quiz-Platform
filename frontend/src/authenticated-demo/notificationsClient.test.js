import { describe, expect, it, vi } from "vitest";

import {
  createNotificationsClient,
  notificationsSocketUrl,
} from "./notificationsClient";

class FakeSocket {
  static instances = [];

  constructor(url) {
    this.url = url;
    this.sent = [];
    FakeSocket.instances.push(this);
  }

  send(value) {
    this.sent.push(JSON.parse(value));
  }

  close() {}

  receive(message) {
    this.onmessage({ data: JSON.stringify(message) });
  }
}

function fakeTimers() {
  const timers = {
    intervals: [],
    timeouts: [],
    setInterval: (fn, ms) => timers.intervals.push({ fn, ms }),
    clearInterval: () => {},
    setTimeout: (fn, ms) => timers.timeouts.push({ fn, ms }),
    clearTimeout: () => {},
  };
  return timers;
}

const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

function start(overrides = {}) {
  FakeSocket.instances = [];
  const timers = fakeTimers();
  const options = {
    url: "ws://test/ws/notifications",
    getToken: vi.fn(async () => "token"),
    onEvent: vi.fn(),
    onReady: vi.fn(),
    onStatus: vi.fn(),
    WebSocketImpl: FakeSocket,
    timers,
    log: () => {},
    ...overrides,
  };
  const client = createNotificationsClient(options);
  return { client, options, timers };
}

describe("notification WebSocket", () => {
  it("builds ws and wss URLs", () => {
    expect(notificationsSocketUrl("http://localhost:8000/")).toBe(
      "ws://localhost:8000/ws/notifications",
    );
    expect(notificationsSocketUrl("https://quiz.example")).toBe(
      "wss://quiz.example/ws/notifications",
    );
    expect(notificationsSocketUrl("/api", "https://quizburg.example")).toBe(
      "wss://quizburg.example/ws/notifications",
    );
    expect(notificationsSocketUrl("/api", "http://localhost:5173")).toBe(
      "ws://localhost:5173/ws/notifications",
    );
  });

  it("authenticates first, pings once ready, and forwards events", async () => {
    const { client, options, timers } = start();
    await flush();
    const socket = FakeSocket.instances[0];
    socket.onopen();
    expect(socket.sent).toEqual([{ type: "auth", token: "token" }]);

    socket.receive({ type: "notifications_ready" });
    expect(options.onReady).toHaveBeenCalledWith({ reconnected: false });
    expect(timers.intervals).toHaveLength(1);
    expect(timers.intervals[0].ms).toBeLessThan(60_000);
    timers.intervals[0].fn();
    expect(socket.sent.at(-1)).toEqual({ type: "ping" });

    socket.receive({ type: "pong" });
    socket.receive({ type: "session_live", class_id: 3, session_id: 9 });
    expect(options.onEvent).toHaveBeenCalledTimes(1);
    expect(options.onEvent).toHaveBeenCalledWith(
      expect.objectContaining({ type: "session_live", class_id: 3 }),
    );
    client.close();
  });

  it("reconnects with backoff after a drop and reports the reconnect", async () => {
    const { client, options, timers } = start();
    await flush();
    FakeSocket.instances[0].receive({ type: "notifications_ready" });
    FakeSocket.instances[0].onclose({ code: 1006 });
    expect(timers.timeouts.map((t) => t.ms)).toEqual([1000]);

    timers.timeouts[0].fn();
    await flush();
    FakeSocket.instances[1].receive({ type: "notifications_ready" });
    expect(options.onReady).toHaveBeenLastCalledWith({ reconnected: true });
    client.close();
  });

  it("does not reconnect when the account is refused (4403)", async () => {
    const { options, timers } = start();
    await flush();
    FakeSocket.instances[0].onclose({ code: 4403 });
    await flush();
    expect(timers.timeouts).toHaveLength(0);
    expect(FakeSocket.instances).toHaveLength(1);
    expect(options.onStatus).toHaveBeenLastCalledWith("stopped");
  });

  it("retries a refused token once with a fresh one, then stops", async () => {
    const { options, timers } = start();
    await flush();
    FakeSocket.instances[0].onclose({ code: 4401 });
    await flush();
    expect(options.getToken).toHaveBeenLastCalledWith({ freshToken: true });
    expect(FakeSocket.instances).toHaveLength(2);

    FakeSocket.instances[1].onclose({ code: 4401 });
    await flush();
    expect(FakeSocket.instances).toHaveLength(2);
    expect(timers.timeouts).toHaveLength(0);
    expect(options.onStatus).toHaveBeenLastCalledWith("stopped");
  });
});
