import { fileURLToPath } from "node:url";
import { expect, test as base } from "@playwright/test";
import { createServer } from "vite";
import { restApi, startE2EServer } from "../e2e/server.js";

export const test = base.extend({
  // eslint-disable-next-line no-empty-pattern -- Playwright requires a destructured fixture argument.
  app: [async ({}, provide) => {
    if (!process.env.E2E_DATABASE_URL) {
      throw new Error("Set E2E_DATABASE_URL to a migrated disposable MySQL test schema.");
    }
    const server = await startE2EServer();
    let vite;
    try {
      vite = await createServer({
        configFile: fileURLToPath(new URL("./vite.config.js", import.meta.url)),
        server: {
          port: 0,
          proxy: {
            "/__test_api": {
              target: server.baseUrl,
              ws: true,
              rewrite: (path) => path.slice("/__test_api".length),
            },
            "/ws": { target: server.baseUrl, ws: true },
          },
        },
      });
      await vite.listen();
      const baseURL = `http://127.0.0.1:${vite.httpServer.address().port}`;
      await provide({ ...server, baseURL });
    } finally {
      try {
        await vite?.close();
      } finally {
        await server.stop();
      }
    }
  }, { scope: "worker", timeout: 40_000 }],

  course: async ({ app, browser }, provide) => {
    const rest = (...args) => restApi(app, ...args);
    const organizer = "prof";
    const owner = "ana";
    const collaborator = "ben";
    const unrelated = "cy";
    const accounts = {};
    for (const person of [organizer, owner, collaborator, unrelated]) {
      accounts[person] = await rest(person, "GET", "/me");
    }
    await rest(organizer, "POST", `/e2e/faculty/${organizer}`);
    const course = await rest(organizer, "POST", "/classes", { name: "Approval and results browser test" });
    const classPath = `/classes/${course.class_id}`;
    for (const person of [owner, collaborator, unrelated]) {
      const membership = await rest(person, "POST", "/classes/join", { code: course.join_code });
      if (membership.membership_status === "REQUESTED") {
        await rest(organizer, "POST", `${classPath}/join-requests/${accounts[person].account_id}/approve`);
      }
    }

    const contexts = [];
    async function newAccountPage(person) {
      const context = await browser.newContext({ baseURL: app.baseURL });
      contexts.push(context);
      await context.addInitScript((token) => {
        window.__quizburgTestToken = token;
      }, app.tokens[person]);
      return context.newPage();
    }

    try {
      await provide({ rest, classPath, accounts, organizer, owner, collaborator, unrelated, newAccountPage });
    } finally {
      await Promise.all(contexts.map((context) => context.close()));
    }
  },
});

export function watchSocket(page, path) {
  const messages = [];
  page.on("websocket", (socket) => {
    const pathname = new URL(socket.url()).pathname.replace(/^\/__test_api/, "");
    if (!pathname.startsWith(path)) return;
    socket.on("framereceived", ({ payload }) => messages.push(JSON.parse(String(payload))));
  });
  return async (expected) => {
    await expect.poll(
      () => messages.some((message) => Object.entries(expected).every(([key, value]) => message[key] === value)),
      { message: `Waiting for ${expected.type} on ${path}` },
    ).toBe(true);
  };
}
