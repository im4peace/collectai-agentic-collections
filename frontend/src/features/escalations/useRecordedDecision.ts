import { useCallback, useEffect, useRef, useState } from "react";
import type { RefObject } from "react";

import type { CaseStatus } from "../../api/escalationsTypes";
import { STATUS_DISPLAY } from "./escalationLabels";

interface RecordedDecision {
  /** Wording of what was decided, e.g. "Reject decision recorded". */
  summary: string;
  /** The case version the decision was made against. */
  versionBefore: number;
}

export interface UseRecordedDecisionResult {
  /** Text for a polite live region: the decision and the case's new status. */
  announcement: string;
  /** Attach to the element that shows the case status; it receives focus. */
  statusRef: RefObject<HTMLDivElement>;
  /** Call right after a decision succeeded, with the version it was made against. */
  markRecorded: (summary: string, versionBefore: number) => void;
}

/**
 * E11-S6 finding F-03 (WCAG 4.1.3 Status Messages, 2.4.3 Focus Order): after a
 * reviewer's decision is recorded, the controls that had focus are gone and
 * nothing said what happened. Once the *reloaded* case arrives (its version
 * differs from the one the decision was made against, so the new status is
 * known) this announces the decision and the new status, and moves focus to the
 * status element -- a stable, meaningful place, never `<body>`.
 *
 * Only a successful decision calls `markRecorded`. A stale-version conflict or
 * an API error never does, so neither announces success nor steals focus; the
 * existing conflict banner and error message are unchanged.
 */
export function useRecordedDecision(
  current: { version: number; status: CaseStatus } | null,
): UseRecordedDecisionResult {
  const [recorded, setRecorded] = useState<RecordedDecision | null>(null);
  const [announcement, setAnnouncement] = useState("");
  const statusRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (recorded === null || current === null || current.version === recorded.versionBefore) {
      return;
    }
    setAnnouncement(`${recorded.summary}. Case status: ${STATUS_DISPLAY[current.status].label}.`);
    statusRef.current?.focus();
    setRecorded(null);
  }, [recorded, current]);

  const markRecorded = useCallback((summary: string, versionBefore: number) => {
    setRecorded({ summary, versionBefore });
  }, []);

  return { announcement, statusRef, markRecorded };
}
