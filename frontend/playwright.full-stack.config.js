import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./browser-tests",
  testMatch: "**/*.full-stack.js",
  workers: 1,
  timeout: 60_000,
  reporter: "list",
  use: { actionTimeout: 12_000, navigationTimeout: 15_000 },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
