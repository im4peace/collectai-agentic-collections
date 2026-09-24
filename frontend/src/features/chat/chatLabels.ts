import type { MessageLabel } from "../../api/chatTypes";

/** Text shown alongside a message that carries the given wire label, never
 * color alone (AC constraint shared with the rest of this codebase's
 * `Badge` convention). `null` means "no extra label for this one". */
export const MESSAGE_LABEL_TEXT: Record<MessageLabel, string> = {
  AI_DISCLOSURE: "AI-generated",
  SIMULATED: "Simulated payment",
  HUMAN_HANDOFF: "Handed off to a specialist",
  SAFE_FALLBACK: "Safe fallback response",
};
