import { expect, test } from "@playwright/test";

const AUTH0_VERIFICATION_URL =
  "https://tenant.example.auth0.com/u/email-verification?ticket=test-ticket";

test("email verification waits for explicit confirmation before opening Auth0", async ({
  page,
}) => {
  let auth0Requests = 0;
  await page.route("https://tenant.example.auth0.com/**", async (route) => {
    auth0Requests += 1;
    await route.fulfill({
      contentType: "text/html",
      body: "<h1>Email verified</h1>",
    });
  });

  await page.goto(`/verify-email#${encodeURIComponent(AUTH0_VERIFICATION_URL)}`);

  await expect(
    page.getByRole("heading", { name: "Confirm your email" }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: /Confirm my email/ })).toBeEnabled();

  // Mail scanners may load the app URL, but that alone must not consume the
  // Auth0 verification ticket.
  await page.waitForTimeout(200);
  expect(auth0Requests).toBe(0);

  await page.getByRole("button", { name: /Confirm my email/ }).click();

  await expect.poll(() => auth0Requests).toBe(1);
  await expect(page).toHaveURL(AUTH0_VERIFICATION_URL);
});

test("email verification rejects an off-tenant redirect target", async ({ page }) => {
  let attackerRequests = 0;
  await page.route("https://attacker.example/**", async (route) => {
    attackerRequests += 1;
    await route.abort();
  });

  const unsafeTarget =
    "https://attacker.example/u/email-verification?ticket=stolen-ticket";
  await page.goto(`/verify-email#${encodeURIComponent(unsafeTarget)}`);

  await expect(
    page.getByRole("heading", { name: "This link doesn't work" }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: /Confirm my email/ })).toHaveCount(0);
  expect(attackerRequests).toBe(0);
});
