import { afterEach, describe, expect, it, vi } from "vitest";

import { copyToClipboard } from "./clipboard";

afterEach(() => {
  vi.unstubAllGlobals();
});

function fakeDocument(copyWorks) {
  const box = {
    value: "",
    style: {},
    setAttribute: vi.fn(),
    select: vi.fn(),
    remove: vi.fn(),
  };
  return {
    box,
    document: {
      createElement: vi.fn(() => box),
      body: { appendChild: vi.fn() },
      execCommand: vi.fn(() => copyWorks),
    },
  };
}

describe("copyToClipboard", () => {
  it("copies the exact text with the clipboard API", async () => {
    const writeText = vi.fn(() => Promise.resolve());
    vi.stubGlobal("navigator", { clipboard: { writeText } });

    await expect(copyToClipboard("482913")).resolves.toBe(true);
    expect(writeText).toHaveBeenCalledWith("482913");
  });

  it("falls back to the copy command when the clipboard API is missing", async () => {
    const { box, document } = fakeDocument(true);
    vi.stubGlobal("navigator", {});
    vi.stubGlobal("document", document);

    await expect(copyToClipboard("482913")).resolves.toBe(true);
    expect(box.value).toBe("482913");
    expect(box.remove).toHaveBeenCalled();
  });

  it("falls back when the clipboard API refuses", async () => {
    const { document } = fakeDocument(true);
    vi.stubGlobal("navigator", {
      clipboard: { writeText: () => Promise.reject(new Error("denied")) },
    });
    vi.stubGlobal("document", document);

    await expect(copyToClipboard("ABCD2345")).resolves.toBe(true);
    expect(document.execCommand).toHaveBeenCalledWith("copy");
  });

  it("reports failure when nothing works", async () => {
    const { document } = fakeDocument(false);
    vi.stubGlobal("navigator", {});
    vi.stubGlobal("document", document);

    await expect(copyToClipboard("482913")).resolves.toBe(false);
  });

  it("does nothing for an empty code", async () => {
    await expect(copyToClipboard("")).resolves.toBe(false);
  });
});
