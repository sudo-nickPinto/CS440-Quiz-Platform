import { defineConfig, devices } from "@playwright/test";

// GitHub Actions sets CI=true.
const ci = Boolean(process.env.CI);

export default defineConfig({
  testDir: "./browser-tests",
  testMatch: "**/*.spec.js",
  fullyParallel: true,
  // A test.only left in by mistake fails CI instead of skipping the others.
  forbidOnly: ci,
  // In CI, print each result to the log and save an HTML report that the
  // workflow uploads when a test fails. Locally keep the default output.
  reporter: ci ? [["list"], ["html", { open: "never" }]] : "list",

  use: {
    baseURL: "http://127.0.0.1:4174",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],

  webServer: {
    command: "npm run dev:browser-test",
    url: "http://127.0.0.1:4174",
    reuseExistingServer: false,
    timeout: 60_000,
  },
});
