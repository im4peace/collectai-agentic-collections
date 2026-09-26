import { useCallback, useRef, useState } from "react";
import type { ReactNode } from "react";

import { ApiError } from "../../api/errors";

/** A message safe to show for any failed demo-control call. */
export function describeDemoError(caught: unknown): string {
  if (caught instanceof ApiError) {
    if (caught.status === 503) {
      return "The audit record could not be written, so nothing was changed. Try again.";
    }
    const { message, reason_code: reasonCode } = caught.body;
    return reasonCode ? `${message} (${reasonCode})` : message;
  }
  return "Could not complete that action. Check that the API is running and try again.";
}

export interface UseDemoActionResult {
  busy: boolean;
  /** The last failure (validation or server), or null. Shown in a
   * persistent `role="alert"` region by each panel. */
  error: string | null;
  /** The last success, shown in a persistent `role="status"` region. */
  notice: ReactNode;
  /** Records a client-side validation failure (and clears any old success). */
  fail: (message: string) => void;
  /** Clears a validation failure once the user has a valid value again. */
  clearError: () => void;
  /**
   * Runs one demo-control call. Ignores a second call while one is in flight
   * (a ref, not state, so a fast double-click cannot slip through before the
   * re-render). Resolves to the call's result, or null if it failed or was
   * ignored. The caller decides what happens next: nothing here is retried.
   */
  run: <T>(call: () => Promise<T>, describeSuccess: (result: T) => ReactNode) => Promise<T | null>;
}

/**
 * Shared busy / error / notice state for one demo-control panel. Every panel
 * keeps its form mounted and never disables the focused button (it uses
 * `aria-disabled` instead), so focus stays where the user left it after an
 * action -- the F-05 pattern the accessibility review recorded is not repeated.
 */
export function useDemoAction(): UseDemoActionResult {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<ReactNode>(null);
  const inFlight = useRef(false);

  const fail = useCallback((message: string) => {
    setNotice(null);
    setError(message);
  }, []);

  const clearError = useCallback(() => setError(null), []);

  const run = useCallback(
    async <T,>(call: () => Promise<T>, describeSuccess: (result: T) => ReactNode) => {
      if (inFlight.current) {
        return null;
      }
      inFlight.current = true;
      setBusy(true);
      setError(null);
      setNotice(null);
      try {
        const result = await call();
        setNotice(describeSuccess(result));
        return result;
      } catch (caught) {
        setError(describeDemoError(caught));
        return null;
      } finally {
        inFlight.current = false;
        setBusy(false);
      }
    },
    [],
  );

  return { busy, error, notice, fail, clearError, run };
}
