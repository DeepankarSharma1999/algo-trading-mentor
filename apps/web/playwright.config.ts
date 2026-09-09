import { defineConfig } from "@playwright/test";

// Runs against a live stack (docker compose up, or `pnpm dev` + engine + postgres). Set E2E_BASE_URL to override.
export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  retries: 0,
  use: { baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000", trace: "retain-on-failure" },
  reporter: [["list"]],
  projects: [{ name: "chromium", use: { browserName: "chromium" } }],
});
