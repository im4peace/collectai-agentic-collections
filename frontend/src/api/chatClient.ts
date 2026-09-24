import { apiFetch } from "./client";
import type {
  CancelProposalResult,
  ChatTurnResponse,
  ConfirmResult,
  ConversationCreateResult,
  ConversationDetail,
  HandoffResult,
} from "./chatTypes";

/** `POST /api/chat/conversations` (CUSTOMER, capability `chat:use`).
 * Starts a new conversation on one of the customer's own accounts and
 * returns the AI-disclosure greeting message (E6-S5 AC1). */
export function createConversation(accountId: string): Promise<ConversationCreateResult> {
  return apiFetch<ConversationCreateResult>("/chat/conversations", {
    method: "POST",
    body: JSON.stringify({ account_id: accountId }),
  });
}

export function getConversation(conversationId: string): Promise<ConversationDetail> {
  return apiFetch<ConversationDetail>(`/chat/conversations/${conversationId}`);
}

/** `POST /api/chat/conversations/{id}/messages`. May reject with `ApiError`
 * whose `body.code === "RATE_LIMITED"` (429) -- callers show a graceful
 * "slow down" message rather than fabricating a reply (E6-S5 AC constraint:
 * never fabricate a reply). */
export function sendMessage(conversationId: string, content: string): Promise<ChatTurnResponse> {
  return apiFetch<ChatTurnResponse>(`/chat/conversations/${conversationId}/messages`, {
    method: "POST",
    body: JSON.stringify({ content }),
  });
}

/** Requires a caller-supplied `idempotencyKey`, unique per confirm attempt.
 * `termsHash` must be the exact `terms_hash` from the displayed `Proposal`
 * -- never edited or hand-typed by the customer. */
export function confirmProposal(
  conversationId: string,
  proposalId: string,
  termsHash: string,
  idempotencyKey: string,
): Promise<ConfirmResult> {
  return apiFetch<ConfirmResult>(
    `/chat/conversations/${conversationId}/proposals/${proposalId}/confirm`,
    {
      method: "POST",
      body: JSON.stringify({ terms_hash: termsHash }),
      headers: { "Idempotency-Key": idempotencyKey },
    },
  );
}

export function cancelProposal(
  conversationId: string,
  proposalId: string,
): Promise<CancelProposalResult> {
  return apiFetch<CancelProposalResult>(
    `/chat/conversations/${conversationId}/proposals/${proposalId}/cancel`,
    { method: "POST" },
  );
}

/** "Talk to a human" (E6-S5 AC2). Requires a caller-supplied
 * `idempotencyKey`, unique per click, so a double-click never opens two
 * cases. */
export function requestHandoff(conversationId: string, idempotencyKey: string): Promise<HandoffResult> {
  return apiFetch<HandoffResult>(`/chat/conversations/${conversationId}/handoff`, {
    method: "POST",
    body: JSON.stringify({}),
    headers: { "Idempotency-Key": idempotencyKey },
  });
}
