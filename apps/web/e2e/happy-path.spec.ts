import { expect, test } from "@playwright/test";

// Onboarding → clone → validate → desk → journal, against a live stack with the seed applied.
const email = `e2e-${Date.now()}@example.com`;
const password = "papertrade123";

test("onboarding → clone → validate → desk → journal", async ({ page }) => {
  // Register: no chart, no desk before the firewall.
  await page.goto("/register");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/onboarding/);
  await expect(page.getByText("The capital firewall")).toBeVisible();

  // Onboarding: buckets + profile, live 1R sentence.
  await page.locator("#safety").fill("500000");
  await page.locator("#long_term").fill("1500000");
  await page.locator("#trading").fill("400000");
  await page.getByRole("radio", { name: "standard" }).check();
  await expect(page.getByTestId("one-r-sentence")).toContainText("2,000");
  await page.getByRole("button", { name: /Sign the firewall/ }).click();
  await expect(page).toHaveURL(/\/desk/);
  await expect(page.getByTestId("strip")).toContainText("1R");
  await expect(page.getByTestId("footer")).toContainText("Not SEBI-registered");

  // Library: templates to learn the schema, clone one.
  await page.goto("/library");
  await expect(page.getByText("Templates to learn the schema").first()).toBeVisible();
  await expect(page.getByText(/recommended/i)).toHaveCount(0);
  await page.getByRole("button", { name: "Clone" }).first().click();
  await expect(page).toHaveURL(/\/builder\/[a-z0-9_]+_v1/);

  // Builder: testable verdict visible, then validate.
  await expect(page.getByText(/TESTABLE/).first()).toBeVisible();
  await page.getByRole("button", { name: "Validate" }).first().click();
  await expect(page).toHaveURL(/\/validation\//, { timeout: 30_000 });
  await expect(page.getByText(/stage/i).first()).toBeVisible();
  // Wait for the job to finish (any terminal state) — the stage list fills in.
  await expect(page.getByText(/(PASS|FAIL|SKIP)/).first()).toBeVisible({ timeout: 85_000 });

  // Desk renders (watchers may be empty for a fresh user; the strip and section must be there).
  await page.goto("/desk");
  await expect(page.getByRole("heading", { name: "Desk" })).toBeVisible();
  await expect(page.getByTestId("strip")).toBeVisible();

  // Journal renders with aggregates.
  await page.goto("/journal");
  await expect(page.getByRole("heading", { name: "Journal" })).toBeVisible();
  await expect(page.getByText(/process/i).first()).toBeVisible();
});

test("seeded demo user sees a rule trace and a populated journal", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill("demo@atm.local");
  await page.getByLabel("Password").fill("papertrade");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/desk/);
  await expect(page.locator(".trace")).toBeVisible();
  await expect(page.locator(".gate").first()).toBeVisible();
  await page.goto("/journal");
  await expect(page.locator("table.ledger-table tbody tr").first()).toBeVisible();
});
