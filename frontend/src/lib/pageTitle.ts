import { useEffect } from "react";

/**
 * Screen-specific document titles (E11-S6 finding F-01, WCAG 2.4.2 Page
 * Titled). Every screen used to share the static `index.html` title
 * "CollectAI", so browser history, tabs and a screen reader's page
 * announcement could not tell screens apart. One place names each screen;
 * each screen calls `usePageTitle` once, so the title follows navigation.
 */
export const APP_TITLE = "CollectAI";

export const SCREEN_TITLES = {
  personaSwitcher: "Persona Switcher",
  portfolio: "Portfolio",
  customer360: "Customer 360",
  escalations: "Escalations",
  escalationCase: "Escalation Case",
  auditTrail: "Audit Trail",
  dashboard: "Dashboard",
  chat: "Chat",
  forbidden: "Forbidden",
} as const;

export type ScreenTitle = (typeof SCREEN_TITLES)[keyof typeof SCREEN_TITLES];

/** `"Dashboard"` -> `"Dashboard | CollectAI"`. */
export function formatPageTitle(screen: string): string {
  return `${screen} | ${APP_TITLE}`;
}

/** Sets `document.title` for the mounted screen. Call it first in a screen
 * component, before any early return, so loading and error states carry the
 * same title as the loaded screen. */
export function usePageTitle(screen: ScreenTitle): void {
  useEffect(() => {
    document.title = formatPageTitle(screen);
  }, [screen]);
}
