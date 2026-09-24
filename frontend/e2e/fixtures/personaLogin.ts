import type { Page } from "@playwright/test";

/**
 * Drives the real persona switcher UI (`/`) to establish a demo session,
 * the same way a person would: pick a persona radio, and for CUSTOMER pick
 * the first seeded demo customer, then submit. Reused by later journeys'
 * e2e specs (specs/design/folder-structure.md: `e2e/fixtures/` "persona
 * login helpers") instead of each spec reimplementing this flow.
 */
export async function loginAsPersona(page: Page, persona: string): Promise<void> {
  await page.goto("/");
  await page.getByRole("radio", { name: new RegExp(persona) }).click();

  if (persona === "CUSTOMER") {
    const select = page.getByRole("combobox");
    const firstRealOption = await select.locator("option").nth(1).getAttribute("value");
    if (firstRealOption) {
      await select.selectOption(firstRealOption);
    }
  }

  await page.getByRole("button", { name: "Use this persona" }).click();
}
