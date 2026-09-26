import { LiveRegion } from "../../components/LiveRegion";
import { ChatComposer } from "./ChatComposer";
import { MessageList } from "./MessageList";
import { ProposalCard } from "./ProposalCard";
import { useChatConversation } from "./useChatConversation";
import { SCREEN_TITLES, usePageTitle } from "../../lib/pageTitle";

function latestAssistantText(messages: { role: string; content: string }[]): string {
  const assistantMessages = messages.filter((message) => message.role === "ASSISTANT");
  return assistantMessages[assistantMessages.length - 1]?.content ?? "";
}

/**
 * E6-S5: the customer-facing AI Collections Chat screen. "Talk to a human"
 * is rendered outside the scrolling message list (`.talk-to-human`, sticky
 * to the top of the chat panel) so it stays visible while scrolling (AC1).
 * New assistant messages are announced through `LiveRegion` (AC7); the
 * pending proposal's Confirm/Cancel actions go through `ConfirmDialog`
 * inside `ProposalCard` for the same reason.
 */
export function ChatScreen(): JSX.Element {
  usePageTitle(SCREEN_TITLES.chat);
  const {
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
  } = useChatConversation();

  if (status === "loading") {
    return (
      <p role="status" aria-live="polite">
        Starting your conversation&hellip;
      </p>
    );
  }

  if (status === "error") {
    return (
      <div className="banner danger" role="alert">
        <div>{errorMessage ?? "Could not start a conversation."}</div>
      </div>
    );
  }

  return (
    <div className="chat-layout">
      <h1 className="sr">AI Collections Chat</h1>
      <LiveRegion message={latestAssistantText(messages)} />

      <div className="talk-to-human">
        <button type="button" className="btn secondary" onClick={() => void talkToHuman()} disabled={handoffBusy}>
          Talk to a human
        </button>
      </div>

      {handoff !== null && (
        <div className="banner info" role="status">
          <div>{handoff.customer_message}</div>
        </div>
      )}

      <MessageList messages={messages} />

      {pendingProposal !== null && (
        <ProposalCard proposal={pendingProposal} busy={sending} onConfirm={() => void confirm()} onCancel={() => void cancel()} />
      )}

      {sendError !== null && (
        <div className="banner danger" role="alert">
          <div>{sendError}</div>
        </div>
      )}

      <ChatComposer disabled={sending} onSend={(content) => void send(content)} />
    </div>
  );
}
