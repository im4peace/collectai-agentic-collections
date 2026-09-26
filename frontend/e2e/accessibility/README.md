# Accessibility verification (E11-S5)

This directory holds the automated accessibility suite: axe scans, keyboard-navigation tests, and focus-management tests, run with Playwright against a real running backend and browser. It is wired into CI as the `e2e` job (`.github/workflows/ci.yml`).

## Scope

- **Axe scans** (zero serious/critical violations): persona switcher, forbidden page, Portfolio, Customer 360, Chat, Escalations (list and case detail), Audit Trail, and the manager Dashboard (`dashboard.spec.ts`, E10-S4: three headed sections, text data-label badges, no mutation controls, keyboard operation, and the forbidden page with no KPI request for every other persona).
- **Keyboard navigation**: every primary journey's interactive controls are reachable and operable without a mouse, with a visible focus indicator (`nav-and-switcher.spec.ts`).
- **Focus management**: dialogs (`ConfirmDialog`, shared by the Record Promise-to-Pay form and the chat proposal Confirm/Cancel UI) move focus in on open, trap it while open, and return it to the trigger on close (`dialogs-and-live-region.spec.ts`). New assistant chat messages are announced through a polite `aria-live` region, not just appended silently.
- **Color is never the only signal**: every AI, rules-engine, risk, priority and simulated-payment state renders through the shared `Badge` component, which requires real text (`color-not-alone.spec.ts`).

## Conformance statement

CollectAI **targets WCAG 2.1 Level AA**. This suite is an automated regression check against that target, not a certification. Passing it means the specific rules axe-core can check mechanically found no serious or critical violations on the screens and journeys covered here, and that the specific keyboard/focus/labelling behaviors this suite exercises work as intended. It does **not** constitute a WCAG 2.1 AA conformance claim: a full conformance audit requires criteria automated tooling cannot verify (for example, some contrast and reflow edge cases, and every success criterion end to end) and typically includes a manual review with assistive technology, which is out of this suite's scope (see `specs/stories/E11-S6.md`, "Manual accessibility review"). That review's checklist, results and findings are in `docs/portfolio/accessibility-review.md`; its checklist is now complete, including a human screen-reader run, but findings remain open, so no conformance is claimed.
