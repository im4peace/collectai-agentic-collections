import { useCallback, useEffect, useState } from "react";

import { getDemoState } from "../../api/demoControlsClient";
import type { DemoState } from "../../api/demoControlsTypes";
import { ApiError } from "../../api/errors";
import { describeDemoError } from "./useDemoAction";

/** `disabled` is a 404: the API's demo-controls flag is off. It is a normal
 * state, not an error. */
export type DemoStateStatus = "loading" | "disabled" | "error" | "ready";

export interface UseDemoStateResult {
  status: DemoStateStatus;
  state: DemoState | null;
  errorMessage: string | null;
  /** Re-reads the state without flashing the loading message (used after an action). */
  reload: () => void;
  /** Re-reads the state after a failure, showing the loading message again. */
  retry: () => void;
}

/**
 * Loads `GET /api/demo-controls/state` once on mount. This is the only
 * request the screen makes by itself: every POST needs an explicit user
 * action, so opening the screen can never advance the clock, reseed, or
 * record a payment.
 */
export function useDemoState(): UseDemoStateResult {
  const [status, setStatus] = useState<DemoStateStatus>("loading");
  const [state, setState] = useState<DemoState | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    getDemoState()
      .then((next) => {
        if (!cancelled) {
          setState(next);
          setErrorMessage(null);
          setStatus("ready");
        }
      })
      .catch((caught: unknown) => {
        if (cancelled) {
          return;
        }
        if (caught instanceof ApiError && caught.status === 404) {
          setState(null);
          setStatus("disabled");
          return;
        }
        setErrorMessage(describeDemoError(caught));
        setStatus("error");
      });
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  const reload = useCallback(() => setReloadKey((key) => key + 1), []);
  const retry = useCallback(() => {
    setStatus("loading");
    setReloadKey((key) => key + 1);
  }, []);

  return { status, state, errorMessage, reload, retry };
}
