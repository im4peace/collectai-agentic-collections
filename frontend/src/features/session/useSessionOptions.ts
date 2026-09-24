import { useEffect, useState } from "react";

import { ApiError } from "../../api/errors";
import { getSessionOptions } from "../../api/client";
import type { SessionOptionsResponse } from "../../api/types";

export interface UseSessionOptionsResult {
  data: SessionOptionsResponse | null;
  error: string | null;
  loading: boolean;
}

/** Loads the switcher's persona list and seeded demo customers
 * (`GET /api/session/options`, public). */
export function useSessionOptions(): UseSessionOptionsResult {
  const [data, setData] = useState<SessionOptionsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getSessionOptions()
      .then((result) => {
        if (!cancelled) {
          setData(result);
          setError(null);
        }
      })
      .catch((caught: unknown) => {
        if (cancelled) {
          return;
        }
        setError(
          caught instanceof ApiError
            ? caught.body.message
            : "Persona options could not be loaded.",
        );
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return { data, error, loading };
}
