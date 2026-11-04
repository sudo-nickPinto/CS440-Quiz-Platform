import { describe, expect, it, vi } from "vitest";

import {
  createQuizEditClient,
  quizEditSocketUrl,
} from "./quizCollaboration";

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
}

describe("quiz collaboration WebSocket", () => {
  it("builds ws and wss URLs", () => {
    expect(quizEditSocketUrl("http://localhost:8000/", 7)).toBe(
      "ws://localhost:8000/ws/quizzes/7",
    );
    expect(quizEditSocketUrl("https://quiz.example", 8)).toBe(
      "wss://quiz.example/ws/quizzes/8",
    );
  });

  it("authenticates and forwards committed question notifications", async () => {
    FakeSocket.instances = [];
    const onMessage = vi.fn();
    const onStatus = vi.fn();
    const client = createQuizEditClient({
      url: "ws://test/ws/quizzes/3",
      getToken: async () => "token",
      onMessage,
      onStatus,
      WebSocketImpl: FakeSocket,
      timers: {
        setInterval: () => 1,
        clearInterval: () => {},
        setTimeout: () => 2,
        clearTimeout: () => {},
      },
    });
    await Promise.resolve();
    const socket = FakeSocket.instances[0];
    socket.onopen();
    socket.onmessage({
      data: JSON.stringify({ type: "quiz_editor_state", quiz_id: 3 }),
    });
    socket.onmessage({
      data: JSON.stringify({
        type: "question_updated",
        quiz_id: 3,
        question: { question_id: 9, revision: 2 },
      }),
    });

    expect(socket.sent[0]).toEqual({ type: "auth", token: "token" });
    expect(onStatus).toHaveBeenCalledWith("open");
    expect(onMessage).toHaveBeenLastCalledWith(
      expect.objectContaining({ type: "question_updated", quiz_id: 3 }),
    );
    client.close();
  });
});
