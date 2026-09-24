import { Badge } from "../../components/Badge";
import { formatDateTime } from "../../lib/formatDateTime";
import type { ChatMessage } from "../../api/chatTypes";
import { MESSAGE_LABEL_TEXT } from "./chatLabels";

export interface MessageListProps {
  messages: ChatMessage[];
}

/** The scrolling message history (E6-S5 AC1). Every `AI_DISCLOSURE`/
 * `SIMULATED`/`HUMAN_HANDOFF`/`SAFE_FALLBACK` label the backend attaches to
 * a message is rendered as visible text, not inferred from role alone. */
export function MessageList({ messages }: MessageListProps): JSX.Element {
  return (
    <div className="chat-messages" aria-label="Conversation">
      {messages.map((message) => (
        <div
          key={message.message_id}
          className={`chat-message ${message.role === "CUSTOMER" ? "customer" : "assistant"}`}
        >
          {message.labels.length > 0 && (
            <div className="row" style={{ marginBottom: 4 }}>
              {message.labels.map((label) => (
                <Badge key={label} text={MESSAGE_LABEL_TEXT[label]} variant="info" />
              ))}
            </div>
          )}
          <p style={{ margin: 0, whiteSpace: "pre-wrap" }}>{message.content}</p>
          <span className="small muted">{formatDateTime(message.created_at)}</span>
        </div>
      ))}
    </div>
  );
}
