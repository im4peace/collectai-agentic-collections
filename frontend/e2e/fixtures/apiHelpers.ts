import type { Page } from "@playwright/test";

/**
 * Reads the current demo session out of the browser's own `sessionStorage`
 * (`auth/sessionStore.ts`'s `STORAGE_KEY`, written by `loginAsPersona`'s
 * real persona-switcher submit) and rebuilds the `X-Persona`/`X-Demo-
 * Session` headers `api/client.ts`'s `personaHeaders()` sends on every
 * request -- so a spec's own `request.get/post` calls (used for setup and
 * assertions the UI itself has no view into, e.g. `GET /api/me/accounts`,
 * demo-controls) authenticate as whichever persona `loginAsPersona` most
 * recently established in that `page`, without hand-rolling a second login.
 */
export async function sessionHeaders(page: Page): Promise<Record<string, string>> {
  const raw = await page.evaluate(() => window.sessionStorage.getItem("collectai.demoSession"));
  if (raw === null) {
    throw new Error("No demo session found in sessionStorage -- call loginAsPersona first.");
  }
  const session = JSON.parse(raw) as {
    persona: string;
    sessionToken: string | null;
  };
  const headers: Record<string, string> = { "X-Persona": session.persona };
  if (session.persona === "CUSTOMER" && session.sessionToken !== null) {
    headers["X-Demo-Session"] = session.sessionToken;
  }
  return headers;
}
