# Manual accessibility review (E11-S6)

CollectAI **targets WCAG 2.1 Level AA**. This document records a manual review of the primary journeys. It does **not** make a conformance claim, and the review is **INCOMPLETE** (see the status block below).

## Review status

| Field | Value |
|---|---|
| Review status | INCOMPLETE |
| Why | Checklist item S3 (a real screen reader) has **not been executed**, and 5 findings (4 MODERATE, 1 MINOR) are still open |
| Conformance statement | None published. The product targets WCAG 2.1 AA (BRD 14.3, D-029) |
| Open CRITICAL findings | 0 |
| Open SERIOUS findings | 0 (F-01, F-02 and F-03 were remediated and re-checked on 2026-09-26) |
| Reviewer | Claude (AI-assisted, tooling-based review) |
| Review date | 2026-09-26 |
| Code reviewed | `feat/domain-foundation` at commit `a102f94` (Group K); F-01 to F-03 re-checked on the remediated working tree |

**Rule for publishing a conformance statement.** A WCAG 2.1 AA conformance statement may be published only when (1) the review is COMPLETE, meaning every checklist item has been executed, including S3 with a real screen reader, and (2) no CRITICAL finding is OPEN. This review applies a stricter house rule as well: no SERIOUS finding may be OPEN either. Until then the README and documentation say "targets WCAG 2.1 AA" and nothing more. `backend/tests/portfolio/test_accessibility_review_doc.py` enforces these rules.

## Who reviewed, and what that means

The review was done by an AI assistant driving Chromium with scripted measurements and reading the results. **No human assistive-technology user took part, and no real screen reader was run.** Everything marked PASS below is a tooling-observed result, not a lived-experience result. That is why S3 is `NOT_EXECUTED` and why the review is incomplete. A human reviewer (or a colleague) should run S3 against the checklist below and record their name and date against it.

## Scope and method

- **Journeys:** A (Promise-to-Pay), B1 (eligible payment arrangement), B2 (financial hardship, including the stale-version conflict) and C (dispute). Each was run end to end as the real personas, in MOCK mode with synthetic data.
- **Screens measured (20):** persona switcher, Portfolio, Customer 360 (plain and hardship account), Chat (idle, proposal, plan options, plan proposal, hardship reply, dispute reply), Confirm dialog, Audit Trail (chain list and timeline), Escalations list, case detail, Reject dialog, dispute panel (open and resolve form), manager Dashboard, and the forbidden page.
- **Environment:** Chromium 153 through Playwright 1.63, Windows 11, viewport 1280 x 720, light and dark colour schemes, a fresh database and stack.
- **Method per checklist item:**
  - **Keyboard (K):** Tab walked through every screen from the top of the document, recording each stop, whether every visible enabled control was reached, and whether focus ever left an open dialog. Operation of the controls is separately proved by the Playwright journey specs.
  - **Contrast (C):** every visible text node's colour was composited over its effective background and compared with 4.5:1 (3:1 for large text), in light and dark. Form-control borders were checked at 3:1, and the focus indicator was checked against its surface.
  - **Zoom (Z):** 200% zoom was emulated as a 640 CSS px viewport (a 1280 px window at 200%), checking page-level horizontal overflow, clipped text and content overflowing its container, with a full-page screenshot inspected for the worst screen.
  - **Focus order (F):** the Tab sequence was compared with the visual order (no backward jumps of more than one row, no positive `tabindex`), and where focus lands after route changes and completed actions was recorded.
  - **Announcements (S1, S2):** a `MutationObserver` recorded text added to `aria-live`, `role="status"` and `role="alert"` regions during each action. This shows what a screen reader **would be handed**, not what it would say.
  - **Structure (extra):** page title, landmarks, heading order, form labels, `lang` and skip link.
- **Automated axe scans** (both colour schemes) were run alongside; in the initial run they found only the issue recorded as F-02 (none remain after its remediation).
- **The harness is not committed.** It was a temporary Playwright script; the method above is enough to repeat it.

## Checklist results

The matrix shows the **current** result of each check. The initial results that changed after remediation are kept in the remediation log below.

Result values: `PASS`, `FAIL (F-nn)` (see the findings), `N/A` (the journey has no such interaction) and `NOT_EXECUTED`.

| ID | Checklist item | Journey A | Journey B1 | Journey B2 | Journey C | Reviewer | Date |
|---|---|---|---|---|---|---|---|
| K1 | Keyboard operation: every interactive control is reachable and operable without a mouse | PASS | PASS | PASS | PASS | Claude (AI-assisted) | 2026-09-26 |
| K2 | Keyboard: a visible focus indicator on every stop, at least 3:1 against its surface | PASS | PASS | PASS | PASS | Claude (AI-assisted) | 2026-09-26 |
| K3 | Keyboard: no trap, and dialogs trap focus, return it on close and stay modal | FAIL (F-06) | FAIL (F-06) | FAIL (F-06) | N/A | Claude (AI-assisted) | 2026-09-26 |
| S1 | Screen-reader announcement (live-region evidence) of chat messages, proposals and confirmations | PASS | PASS | PASS | PASS | Claude (AI-assisted) | 2026-09-26 |
| S2 | Screen-reader announcement (live-region evidence) of review actions and outcomes | FAIL (F-04) | N/A | PASS | PASS | Claude (AI-assisted) | 2026-09-26 |
| S3 | Screen-reader announcement with a real screen reader (NVDA, JAWS, VoiceOver or Narrator) | NOT_EXECUTED | NOT_EXECUTED | NOT_EXECUTED | NOT_EXECUTED | not yet run | not yet run |
| C1 | Contrast: text at least 4.5:1 (3:1 large), light scheme | PASS | PASS | PASS | PASS | Claude (AI-assisted) | 2026-09-26 |
| C2 | Contrast: text at least 4.5:1 (3:1 large), dark scheme | PASS | PASS | PASS | PASS | Claude (AI-assisted) | 2026-09-26 |
| C3 | Contrast: non-text (form-control borders, focus indicators) at least 3:1 | PASS | PASS | PASS | PASS | Claude (AI-assisted) | 2026-09-26 |
| Z1 | Zoom to 200 percent: no loss of content or functionality | PASS | PASS | FAIL (F-07) | PASS | Claude (AI-assisted) | 2026-09-26 |
| F1 | Focus order: logical, matching the visual and DOM order | PASS | PASS | PASS | PASS | Claude (AI-assisted) | 2026-09-26 |
| F2 | Focus management: focus is kept somewhere sensible after navigation and completed actions | FAIL (F-05) | FAIL (F-05) | FAIL (F-05) | FAIL (F-05) | Claude (AI-assisted) | 2026-09-26 |
| P1 | Structure (extra): descriptive page title, landmarks, one h1, labelled controls, `lang`, bypass mechanism | PASS | PASS | PASS | PASS | Claude (AI-assisted) | 2026-09-26 |

### Evidence behind the results

- **K1.** Every visible enabled control was reached by Tab on all 20 screens; the only controls not reached are the second and third radios of the persona-switcher group, which is correct (arrow keys move within a radio group). Initially it failed where a scroll container could not be focused (F-02): the chat transcript on the B1 plan-proposal screen and a table wrapper on the B2 hardship Customer 360. **After remediation** both are named, focusable regions while they overflow, and axe reports no `scrollable-region-focusable` violation on any of the 20 screens.
- **K2.** 198 tab stops were measured across the screens and each had a visible indicator; the lowest indicator contrast was 5.57:1. The date inputs on the Audit screen were first flagged as having no indicator, but a targeted probe and a screenshot show a solid 3 px ring, so that was a measurement artefact and is not a finding.
- **K3.** Tab inside an open dialog cycles between the dialog's own controls, Escape closes it, and focus returns to the control that opened it. But when a pointer user clicks the area outside the Confirm dialog (which stays open) and then presses Tab, focus goes to the controls **behind** it before returning (F-06). The Reject dialog uses the same component, so the same weakness applies to B2.
- **S1.** The assistant's reply, the proposal text, the confirmation result, and the hardship and dispute replies each appear as a change in a polite live region (`role="status"`). The stale-version conflict is a `role="alert"`.
- **S2.** Dispute "Start review" and "Resolve" are announced ("Dispute review started.", "Dispute resolved.", `role="status"`). Initially a reviewer's decision was **not** announced at all (F-03); **after remediation** it is announced ("Reject decision recorded. Case status: DECIDED.") in a polite status region. The Audit search still announces only "Searching…" and never the result (F-04, open).
- **C1–C3.** 1,444 visible text nodes were measured in the light scheme and the same screens again in dark: zero failures in either. No form-control border fell below 3:1.
- **Z1.** No horizontal page overflow or clipping at 200% on 19 of the 20 screens. On the B2 hardship Customer 360 the page overflows horizontally, and a value in the factors table is cut off (`CONTACT_…`) inside a scroll region a keyboard user cannot focus (F-07, with F-02).
- **F1.** No backward jumps in any tab sequence and no positive `tabindex` anywhere; the order follows the document order.
- **F2.** Focus is lost to `<body>` after opening a case from the list, after a confirmation completes, after a reviewer decision, and after the dispute actions, because the control that had focus is removed from the page (F-05). After clicking a navigation link, focus correctly stays on that link.
- **P1.** Initially every screen had the same title, "CollectAI" (F-01); **after remediation** the 20 screens carry 9 distinct titles such as "Escalations | CollectAI". Landmarks (banner, navigation, main) are present, there is exactly one `h1` per screen, no heading level is skipped, every form control has a label, and `lang="en"` is set. There is no skip link; the landmarks satisfy the bypass requirement, so that is recorded as the minor F-08.

## Findings

Severity scale: **CRITICAL** blocks a primary task with no workaround; **SERIOUS** fails a WCAG A or AA criterion or makes a primary task significantly harder, with a workaround; **MODERATE** is a limited failure or an inconvenience; **MINOR** is a best-practice gap. Status values: `OPEN`, `RESOLVED` (fixed and re-validated, with the date and evidence recorded), `ACCEPTED` (deliberately not fixing, with a reason).

| ID | Title | Severity | Status | WCAG SC | Journeys | Evidence | Proposed fix | Remediation and validation | Validated on |
|---|---|---|---|---|---|---|---|---|---|
| F-01 | Every screen has the same page title "CollectAI" | SERIOUS | RESOLVED | 2.4.2 Page Titled | A, B1, B2, C | `document.title` is "CollectAI" on all 20 screens measured, so a screen reader or browser history cannot tell screens apart | Set a descriptive `document.title` per route (for example "Escalations - CollectAI") | Added `lib/pageTitle.ts` (one title per screen plus `usePageTitle`, called first in each screen component). Vitest covers uniqueness and navigation; Playwright confirms the title after each navigation; the re-run shows 9 distinct titles across the 20 screens | 2026-09-26 |
| F-02 | Scrollable regions cannot be reached by keyboard | SERIOUS | RESOLVED | 2.1.1 Keyboard | B1, B2 (also A, C latently) | axe `scrollable-region-focusable` (serious) on the chat transcript `.chat-messages` and on a table wrapper `.tablewrap`; a keyboard user cannot scroll either | Give scrollable containers `tabindex="0"`, a role and an accessible name | Added `components/ScrollRegion.tsx`: the chat transcript and the table wrappers become `role="region"` with a name and `tabindex=0` only while they overflow, and add no tab stop otherwise. Vitest, Playwright (Tab reaches it, focus ring visible, PageDown and ArrowDown scroll it) and axe (rule `scrollable-region-focusable`) pass; the re-run shows 0 axe violations on 20 screens | 2026-09-26 |
| F-03 | A reviewer's decision is not announced, and focus is lost | SERIOUS | RESOLVED | 4.1.3 Status Messages | B2 | After Reject, no live region changes; the status badge becomes DECIDED and the decision controls disappear silently | Announce the outcome ("Decision recorded") in a polite status region and move focus to a sensible target | Added `useRecordedDecision`: once the reloaded case arrives, a polite status region announces "<Action> decision recorded. Case status: <status>." and focus moves to the "Case status" group. A stale-version conflict or an API error announces no success and does not move focus; the conflict alert, refetch and no-retry behaviour are unchanged. Vitest and Playwright pass; the re-run shows the announcement and focus on "Case status" | 2026-09-26 |
| F-04 | Search and load results are not announced | MODERATE | OPEN | 4.1.3 Status Messages | A, B2 | Audit search announces only "Searching…"; the Dashboard and case detail announce "Loading…" but not that content arrived | Announce the result count or "Loaded" when data arrives | - | - |
| F-05 | Focus falls to the page body after navigation and completed actions | MODERATE | OPEN | 2.4.3 Focus Order | A, B1, B2, C | Opening a case, confirming a proposal, recording a decision and the dispute actions each leave `document.activeElement` on `<body>` | Move focus to the new heading or a status message after such actions | - | - |
| F-06 | Controls behind a modal dialog can be reached after a backdrop click | MODERATE | OPEN | 2.4.3 Focus Order | A, B1, B2 | With the Confirm dialog open, click outside it, then Tab x6: focus visits "Talk to a human", the page's "Confirm" and "Cancel", then re-enters the dialog | Make the background inert while a dialog is open, or pull focus back into it | - | - |
| F-07 | Customer 360 overflows horizontally at 200% zoom | MODERATE | OPEN | 1.4.4 Resize Text | B2 | At 640 CSS px the page scrolls horizontally, profile content is wider than the viewport and a factors-table value is cut off | Let the profile row and panels wrap; make the table region focusable (see F-02) | - | - |
| F-08 | No skip link | MINOR | OPEN | 2.4.1 Bypass Blocks (met by landmarks) | A, B1, B2, C | Banner, navigation and main landmarks exist, which satisfies the criterion; a skip-to-content link would help | Add a visible-on-focus "Skip to main content" link | - | - |

## Remediation log (F-01, F-02, F-03)

On 2026-09-26 the three SERIOUS findings were remediated in the frontend and re-checked. The findings are kept above (severity unchanged, status `RESOLVED`). F-04 to F-08 were deliberately **not** touched and remain `OPEN`.

Re-check method: focused Vitest tests, targeted Playwright and axe checks against the real stack, and a re-run of the same measurement harness as the initial review on a fresh database. These are automated checks, **not** screen-reader testing.

| Checklist item | Journey | Initial result | Result now | What changed |
|---|---|---|---|---|
| K1 | B1 | FAIL (F-02) | PASS | The chat transcript is a focusable, named region while it scrolls |
| K1 | B2 | FAIL (F-02) | PASS | The factors-table wrapper is a focusable, named region while it scrolls |
| S2 | B2 | FAIL (F-03) | PASS | The decision result is announced and focus moves to "Case status" |
| P1 | A, B1, B2, C | FAIL (F-01) | PASS | Each screen has its own title (bypass is met by landmarks; F-08 stays an open minor best-practice gap) |

Unchanged by the re-run: contrast (0 failures in either scheme), tab order (no backward jumps), the announcements for chat and dispute actions, and the still-open F-04 to F-08. Tab stops did not grow anywhere except the two overflowing regions above; the short chat and the tables that fit have no new stop.

## What this review does not cover

- **A real screen reader.** Not executed (S3). This is the main reason the review is incomplete.
- **400% zoom and reflow at 320 CSS px (1.4.10),** text-spacing overrides (1.4.12), and forced-colours or high-contrast modes.
- **Touch and mobile,** although the customer chat is meant to be responsive.
- **Other browsers** (only Chromium was used).
- **Criteria outside the checklist:** every other WCAG 2.1 success criterion is unreviewed, so absence of a finding is not evidence of conformance.
- **Screens outside the four journeys** or states not reached: for example the Record Promise-to-Pay dialog and Portfolio filtering with assistive technology.

## Next steps

1. Run S3 with a real screen reader on Journeys A, B1, B2 and C and record the reviewer and date against S3. This is the main remaining blocker.
2. Decide whether to fix the open MODERATE and MINOR findings (F-04 to F-08). Each fix should re-run the affected checklist item and update the finding's status here.
3. Only when S3 is done, no CRITICAL is open and (by the house rule) no SERIOUS is open, change the review status to COMPLETE and consider a conformance statement. The two conditions on findings hold today; S3 does not, so the review stays INCOMPLETE and the product continues to state only that it targets WCAG 2.1 AA.
