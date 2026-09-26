import type { ReactNode } from "react";

export interface DemoFeedbackProps {
  /** The id a field can point `aria-describedby` at. */
  errorId: string;
  error: string | null;
  notice: ReactNode;
}

/**
 * The result area every demo-control panel ends with. Both live regions are
 * rendered on first paint and stay in the page: a screen reader only
 * announces a live region whose *content* changes, so mounting one together
 * with its message (the F-04 pattern in the accessibility review) is not
 * reliably announced. Errors are `role="alert"`, successes `role="status"`.
 * Nothing here relies on colour: each message is text.
 */
export function DemoFeedback({ errorId, error, notice }: DemoFeedbackProps): JSX.Element {
  return (
    <>
      <div id={errorId} role="alert">
        {error !== null && (
          <div className="banner danger">
            <div>{error}</div>
          </div>
        )}
      </div>
      <div role="status" aria-live="polite">
        {notice !== null && notice !== undefined && (
          <div className="banner info">
            <div>{notice}</div>
          </div>
        )}
      </div>
    </>
  );
}
