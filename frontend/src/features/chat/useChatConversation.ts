import { useCallback, useEffect, useState } from "react";

import {
  cancelProposal as apiCancelProposal,
  confirmProposal as apiConfirmProposal,
  createConversation,
  requestHandoff as apiRequestHandoff,
  sendMessage as apiSendMessage,
} from "../../api/chatClient";
import { ApiError } from "../../api/errors";
import { getMyAccounts } from "../../api/meClient";
import type { ChatMessage, EscalationCustomerView, Proposal } from "../../api/chatTypes";

export type ChatStatus = "loading" | "ready" | "error";

export interface UseChatConversationResult {
  status: ChatStatus;
  errorMessage: string | null;
  messages: ChatMessage[];
  pendingProposal: Proposal | null;
  handoff: EscalationCustomerView | null;
  sending: boolean;
  sendError: string | null;
  handoffBusy: boolean;
  send: (content: string) => Promise<void>;
  confirm: () => Promise<void>;
  cancel: () => Promise<void>;
  talkToHuman: () => Promise<void>;
}

function messageFromApiError(caught: unknown, fallback: string): string {
  return caught instanceof ApiError ? caught.body.message : fallback;
}

/**
 * Starts (or resumes) the customer's chat conversation and exposes every
 * action E6-S5 needs (send, confirm/cancel a proposal, "Talk to a human"),
 * mirroring `usePortfolioQuery`'s "one hook owns the data-fetching effect
 * plus its own explicit error branches" shape. Account selection is
 * simplified per this story's handback notes: a CUSTOMER persona's first
 * account (`GET /api/me/accounts`) is used automatically rather than
 * building a separate account-picker screen, since the demo always seeds
 * exactly one account per customer.
 */
export function useChatConversation(): UseChatConversationResult {
  const [status, setStatus] = useState<ChatStatus>("loading");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [pendingProposal, setPendingProposal] = useState<Proposal | null>(null);
  const [handoff, setHandoff] = useState<EscalationCustomerView | null>(null);
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const [handoffBusy, setHandoffBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function start(): Promise<void> {
      try {
        const accounts = await getMyAccounts();
        const [firstAccount] = accounts.items;
        if (firstAccount === undefined) {
          throw new Error("No account is available to start a conversation.");
        }
        const created = await createConversation(firstAccount.account_id);
        if (cancelled) return;
        setConversationId(created.conversation.conversation_id);
        setMessages([created.greeting]);
        setStatus("ready");
      } catch (caught) {
        if (cancelled) return;
        setStatus("error");
        setErrorMessage(messageFromApiError(caught, "Could not start a conversation."));
      }
    }
    void start();
    return () => {
      cancelled = true;
    };
  }, []);

  const send = useCallback(
    async (content: string): Promise<void> => {
      if (conversationId === null) return;
      setSending(true);
      setSendError(null);
      try {
        const turn = await apiSendMessage(conversationId, content);
        setMessages((previous) => [...previous, turn.customer_message, turn.assistant_message]);
        setPendingProposal(turn.proposal);
        if (turn.handoff !== null) {
          setHandoff(turn.handoff);
        }
      } catch (caught) {
        const isRateLimited = caught instanceof ApiError && caught.body.code === "RATE_LIMITED";
        setSendError(
          isRateLimited
            ? "You're sending messages too quickly. Please wait a moment and try again."
            : messageFromApiError(caught, "Could not send that message."),
        );
      } finally {
        setSending(false);
      }
    },
    [conversationId],
  );

  const confirm = useCallback(async (): Promise<void> => {
    if (conversationId === null || pendingProposal === null) return;
    setSending(true);
    setSendError(null);
    try {
      const result = await apiConfirmProposal(
        conversationId,
        pendingProposal.proposal_id,
        pendingProposal.terms_hash,
        crypto.randomUUID(),
      );
      setMessages((previous) => [...previous, result.assistant_message]);
      setPendingProposal(null);
    } catch (caught) {
      setSendError(messageFromApiError(caught, "Could not confirm that proposal."));
    } finally {
      setSending(false);
    }
  }, [conversationId, pendingProposal]);

  const cancel = useCallback(async (): Promise<void> => {
    if (conversationId === null || pendingProposal === null) return;
    setSending(true);
    setSendError(null);
    try {
      const result = await apiCancelProposal(conversationId, pendingProposal.proposal_id);
      setMessages((previous) => [...previous, result.assistant_message]);
      setPendingProposal(null);
    } catch (caught) {
      setSendError(messageFromApiError(caught, "Could not cancel that proposal."));
    } finally {
      setSending(false);
    }
  }, [conversationId, pendingProposal]);

  const talkToHuman = useCallback(async (): Promise<void> => {
    if (conversationId === null) return;
    setHandoffBusy(true);
    setSendError(null);
    try {
      const result = await apiRequestHandoff(conversationId, crypto.randomUUID());
      setMessages((previous) => [...previous, result.assistant_message]);
      setHandoff(result.escalation);
    } catch (caught) {
      setSendError(messageFromApiError(caught, "The handoff could not be completed. Please try again."));
    } finally {
      setHandoffBusy(false);
    }
  }, [conversationId]);

  return {
    status,
    errorMessage,
    messages,
    pendingProposal,
    handoff,
    sending,
    sendError,
    handoffBusy,
    send,
    confirm,
    cancel,
    talkToHuman,
  };
}
