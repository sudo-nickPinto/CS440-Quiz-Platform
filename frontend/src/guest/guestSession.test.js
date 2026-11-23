import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  clearGuestToken,
  getGuestQuizPath,
  getGuestToken,
  pickTokenGetter,
  setGuestToken,
} from "./guestSession";

// Node has no sessionStorage; a small in-memory stand-in.
beforeEach(() => {
  const store = new Map();
  vi.stubGlobal("sessionStorage", {
    getItem: (key) => (store.has(key) ? store.get(key) : null),
    setItem: (key, value) => store.set(key, String(value)),
    removeItem: (key) => store.delete(key),
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("guest token", () => {
  it("remembers the one game the guest joined", () => {
    expect(getGuestQuizPath()).toBe("");
    setGuestToken("guest_abc", 42);
    expect(getGuestQuizPath()).toBe("/app/play/42");
    clearGuestToken();
    expect(getGuestQuizPath()).toBe("");
  });

  it("is stored, read and cleared", () => {
    expect(getGuestToken()).toBe("");
    setGuestToken("guest_abc");
    expect(getGuestToken()).toBe("guest_abc");
    clearGuestToken();
    expect(getGuestToken()).toBe("");
  });

  it("is used only while nobody is signed in with Auth0", async () => {
    const auth0 = vi.fn(async () => "auth0-token");

    expect(pickTokenGetter(false, auth0)).toBe(auth0);

    setGuestToken("guest_abc");
    expect(await pickTokenGetter(false, auth0)({ freshToken: true })).toBe(
      "guest_abc",
    );
    expect(pickTokenGetter(true, auth0)).toBe(auth0);
    expect(auth0).not.toHaveBeenCalled();
  });

  it("falls back to Auth0 when storage is blocked", () => {
    vi.stubGlobal("sessionStorage", {
      getItem: () => {
        throw new Error("blocked");
      },
    });
    const auth0 = vi.fn();
    expect(getGuestToken()).toBe("");
    expect(pickTokenGetter(false, auth0)).toBe(auth0);
  });
});
