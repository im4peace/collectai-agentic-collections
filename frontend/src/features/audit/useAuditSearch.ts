import { useState } from "react";

import { listAuditChains, searchAuditEvents } from "../../api/auditClient";
import { ApiError } from "../../api/errors";
import type { AuditChainSummary, AuditEvent } from "../../api/auditTypes";

export interface AuditSearchFilters {
  correlationId: string;
  accountId: string;
  from: string;
  to: string;
}

export const EMPTY_AUDIT_FILTERS: AuditSearchFilters = {
  correlationId: "",
  accountId: "",
  from: "",
  to: "",
};

export type AuditSearchStatus = "idle" | "loading" | "chain-list" | "timeline" | "error";

export interface UseAuditSearchResult {
  status: AuditSearchStatus;
  chains: AuditChainSummary[];
  timeline: AuditEvent[];
  errorMessage: string | null;
  /** AC1: a correlation_id search (directly, or by picking a chain from a
   * broader account_id/date search) shows that chain's ordered timeline. */
  search: (filters: AuditSearchFilters) => void;
  openChain: (correlationId: string) => void;
}

/**
 * E9-S2 AC1: searching by account id or correlation id shows the decision
 * chain. A correlation_id search goes straight to `GET /api/audit`
 * (already ordered by (timestamp, sequence), per api-contracts.md and
 * `audit/queries.search`); an account_id/date-only search has no single
 * chain to show yet, so it lists chain summaries via
 * `GET /api/audit/chains` first -- `openChain` then fetches that chain's
 * own timeline, the same request a direct correlation_id search makes.
 */
export function useAuditSearch(): UseAuditSearchResult {
  const [status, setStatus] = useState<AuditSearchStatus>("idle");
  const [chains, setChains] = useState<AuditChainSummary[]>([]);
  const [timeline, setTimeline] = useState<AuditEvent[]>([]);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  function fail(caught: unknown, fallback: string): void {
    setStatus("error");
    setErrorMessage(caught instanceof ApiError ? caught.body.message : fallback);
  }

  function openChain(correlationId: string): void {
    setStatus("loading");
    searchAuditEvents({ correlation_id: correlationId })
      .then((page) => {
        setTimeline(page.items);
        setStatus("timeline");
      })
      .catch((caught: unknown) => fail(caught, "This chain could not be loaded."));
  }

  function search(filters: AuditSearchFilters): void {
    const correlationId = filters.correlationId.trim();
    const accountId = filters.accountId.trim();
    const from = filters.from.trim();
    const to = filters.to.trim();

    if (correlationId !== "") {
      openChain(correlationId);
      return;
    }

    setStatus("loading");
    listAuditChains({
      account_id: accountId === "" ? undefined : accountId,
      from: from === "" ? undefined : new Date(from).toISOString(),
      to: to === "" ? undefined : new Date(to).toISOString(),
    })
      .then((page) => {
        setChains(page.items);
        setStatus("chain-list");
      })
      .catch((caught: unknown) => fail(caught, "The audit trail could not be searched."));
  }

  return { status, chains, timeline, errorMessage, search, openChain };
}
