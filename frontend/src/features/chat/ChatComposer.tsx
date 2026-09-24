import type { FormEvent, KeyboardEvent } from "react";
import { useState } from "react";

export interface ChatComposerProps {
  disabled: boolean;
  onSend: (content: string) => void;
}

const MAX_LENGTH = 2000;

/** The message input (E6-S5 AC constraint: keyboard-only sending must work
 * -- Enter to send from a text input, or an accessible Send button). A
 * plain `<form onSubmit>` gives both for free: Enter inside the textarea
 * submits the form, and the Send button is a real `type="submit"` control
 * reachable by Tab. Shift+Enter still inserts a newline. */
export function ChatComposer({ disabled, onSend }: ChatComposerProps): JSX.Element {
  const [value, setValue] = useState("");

  function submit(): void {
    const trimmed = value.trim();
    if (trimmed === "" || disabled) {
      return;
    }
    onSend(trimmed);
    setValue("");
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    submit();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>): void {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  }

  return (
    <form className="chat-composer" onSubmit={handleSubmit}>
      <label className="sr" htmlFor="chat-composer-input">
        Message
      </label>
      <textarea
        id="chat-composer-input"
        value={value}
        maxLength={MAX_LENGTH}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        placeholder="Type a message…"
      />
      <button type="submit" className="btn" disabled={disabled || value.trim() === ""}>
        Send
      </button>
    </form>
  );
}
