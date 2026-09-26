import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as client from "../../api/escalationsClient";
import { ESCALATIONS_PAGE_LIMIT, useEscalationsQuery } from "./useEscalationsQuery";

vi.mock("../../api/escalationsClient", () => ({ getEscalations: vi.fn() }));

describe("useEscalationsQuery", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("never asks for more rows than the API allows (a larger limit is a 422 and the queue fails to load)", async () => {
    vi.mocked(client.getEscalations).mockResolvedValue({
      items: [],
      page: { limit: ESCALATIONS_PAGE_LIMIT, offset: 0, total: 0 },
      policy_version: "policy-v1",
    });

    const { result } = renderHook(() => useEscalationsQuery());
    await waitFor(() => expect(result.current.status).toBe("loaded"));

    expect(ESCALATIONS_PAGE_LIMIT).toBeLessThanOrEqual(50);
    expect(client.getEscalations).toHaveBeenCalledWith(
      expect.objectContaining({ limit: ESCALATIONS_PAGE_LIMIT }),
    );
  });
});
