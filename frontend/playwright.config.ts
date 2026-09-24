import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright config for the frontend's e2e suite (specs/design/
 * folder-structure.md section 3: `frontend/e2e/`). Story E3-S4 is the
 * first UI story with real accessibility (AC3, AC5) and keyboard
 * acceptance criteria, so this is the first Playwright config in the repo.
 *
 * `webServer` starts the Vite dev server so `npx playwright test` works
 * standalone; the backend API it proxies to (`/api` -> localhost:8000,
 * see `vite.config.ts`) must already be running separately (Makefile's
 * `up`/`migrate`/`seed`), since these are journeys against a real seeded
 * demo backend, not a mocked one.
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: "list",
  use: {
    baseURL: "http://localhost:5173",
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    command: "npm run dev",
    url: "http://localhost:5173",
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
});
