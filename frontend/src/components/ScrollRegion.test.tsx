import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import type { ChatMessage } from "../api/chatTypes";
import { MessageList } from "../features/chat/MessageList";
import { DataTable } from "./DataTable";
import { ScrollRegion } from "./ScrollRegion";

/**
 * jsdom has no layout, so overflow is faked: while `overflowing` is true, every
 * scroll container (`.tablewrap`, `.chat-messages`, `.box`) reports content
 * taller than its box. The window `resize` event -- which `ScrollRegion` also
 * listens for -- makes it re-measure.
 */
let overflowing = false;
const isScrollBox = (el: HTMLElement): boolean =>
  el.classList.contains("tablewrap") ||
  el.classList.contains("chat-messages") ||
  el.classList.contains("box");
const original = {
  scrollHeight: Object.getOwnPropertyDescriptor(HTMLElement.prototype, "scrollHeight"),
  clientHeight: Object.getOwnPropertyDescriptor(HTMLElement.prototype, "clientHeight"),
};

function setOverflow(value: boolean): void {
  overflowing = value;
  act(() => {
    fireEvent(window, new Event("resize"));
  });
}

beforeEach(() => {
  overflowing = false;
  Object.defineProperty(HTMLElement.prototype, "scrollHeight", {
    configurable: true,
    get(this: HTMLElement) {
      return overflowing && isScrollBox(this) ? 500 : 100;
    },
  });
  Object.defineProperty(HTMLElement.prototype, "clientHeight", {
    configurable: true,
    get() {
      return 100;
    },
  });
});

afterEach(() => {
  for (const [name, descriptor] of Object.entries(original)) {
    if (descriptor) Object.defineProperty(HTMLElement.prototype, name, descriptor);
    else delete (HTMLElement.prototype as unknown as Record<string, unknown>)[name];
  }
});

describe("ScrollRegion (E11-S6 F-02, WCAG 2.1.1)", () => {
  it("adds no tab stop, role or name while nothing overflows", () => {
    render(
      <ScrollRegion className="box" label="Big table">
        <p>short</p>
      </ScrollRegion>,
    );

    const box = screen.getByText("short").parentElement as HTMLElement;
    expect(box).not.toHaveAttribute("tabindex");
    expect(box).not.toHaveAttribute("role");
    expect(screen.queryByRole("region")).not.toBeInTheDocument();
  });

  it("becomes a named, focusable region while its content overflows", async () => {
    overflowing = true;
    render(
      <ScrollRegion className="box" label="Big table">
        <p>long</p>
      </ScrollRegion>,
    );

    const region = await screen.findByRole("region", { name: "Big table" });
    expect(region).toHaveAttribute("tabindex", "0");
  });

  it("follows the content: focusable once it overflows, plain again when it stops", async () => {
    render(
      <ScrollRegion className="box" label="Growing">
        <p>text</p>
      </ScrollRegion>,
    );
    expect(screen.queryByRole("region")).not.toBeInTheDocument();

    setOverflow(true);
    await waitFor(() =>
      expect(screen.getByRole("region", { name: "Growing" })).toHaveAttribute("tabindex", "0"),
    );

    setOverflow(false);
    await waitFor(() => expect(screen.queryByRole("region")).not.toBeInTheDocument());
  });

  it("re-measures when children are added (a transcript growing inside a fixed height)", async () => {
    function Harness({ count }: { count: number }): JSX.Element {
      return (
        <ScrollRegion className="box" label="Transcript">
          {Array.from({ length: count }, (_, i) => (
            <p key={i}>line {i}</p>
          ))}
        </ScrollRegion>
      );
    }
    const { rerender } = render(<Harness count={1} />);
    expect(screen.queryByRole("region")).not.toBeInTheDocument();

    overflowing = true; // the box is now too small for its content...
    rerender(<Harness count={5} />); // ...and new children trigger the re-measure
    await waitFor(() => expect(screen.getByRole("region", { name: "Transcript" })).toBeInTheDocument());
  });

  it("is reached by Tab when it overflows, and skipped when it does not", async () => {
    const user = userEvent.setup();
    overflowing = true;
    const first = render(
      <>
        <button type="button">before</button>
        <ScrollRegion className="box" label="Big table">
          <p>long</p>
        </ScrollRegion>
      </>,
    );
    await screen.findByRole("region", { name: "Big table" });
    await user.tab();
    expect(screen.getByRole("button", { name: "before" })).toHaveFocus();
    await user.tab();
    expect(screen.getByRole("region", { name: "Big table" })).toHaveFocus();
    first.unmount();

    overflowing = false;
    render(
      <>
        <button type="button">before</button>
        <ScrollRegion className="box" label="Big table">
          <p>short</p>
        </ScrollRegion>
        <button type="button">after</button>
      </>,
    );
    await user.tab();
    await user.tab();
    expect(screen.getByRole("button", { name: "after" })).toHaveFocus();
  });

  it("alwaysNamed keeps the region name but never adds a tab stop by itself", () => {
    render(
      <ScrollRegion className="chat-messages" label="Conversation" alwaysNamed>
        <p>hi</p>
      </ScrollRegion>,
    );

    expect(screen.getByRole("region", { name: "Conversation" })).not.toHaveAttribute("tabindex");
  });
});

function message(id: string, content: string): ChatMessage {
  return {
    message_id: id,
    conversation_id: "conv_1",
    role: "ASSISTANT",
    content,
    content_source: "TEMPLATE",
    labels: [],
    created_at: "2026-10-01T09:00:00Z",
  };
}

interface Row {
  id: string;
}
const columns = [{ key: "id", header: "Id", renderCell: (row: Row) => row.id }];

describe("the identified scroll regions use it", () => {
  it("chat transcript: always named 'Conversation'; a tab stop only while it scrolls", async () => {
    render(<MessageList messages={[message("m1", "Hello")]} />);
    expect(screen.getByRole("region", { name: "Conversation" })).not.toHaveAttribute("tabindex");

    setOverflow(true);
    await waitFor(() =>
      expect(screen.getByRole("region", { name: "Conversation" })).toHaveAttribute("tabindex", "0"),
    );
  });

  it("table wrapper: a plain wrapper when it fits; a named, focusable region when it overflows", async () => {
    const { container } = render(
      <DataTable columns={columns} rows={[{ id: "a" }]} getRowKey={(r) => r.id} caption="Accounts list" />,
    );
    expect(container.querySelector(".tablewrap")).not.toHaveAttribute("tabindex");
    expect(screen.queryByRole("region")).not.toBeInTheDocument();

    setOverflow(true);
    // Named from its text caption by default...
    await waitFor(() =>
      expect(screen.getByRole("region", { name: "Accounts list" })).toHaveAttribute("tabindex", "0"),
    );
  });

  it("table wrapper: regionLabel overrides the caption as the region's name", async () => {
    render(
      <DataTable
        columns={columns}
        rows={[{ id: "a" }]}
        getRowKey={(r) => r.id}
        caption="12 of 40 accounts, sorted by dpd desc"
        regionLabel="Delinquent accounts"
      />,
    );

    setOverflow(true);
    await waitFor(() => expect(screen.getByRole("region", { name: "Delinquent accounts" })).toBeInTheDocument());
  });

  it("a page with only short content gains no extra tab stops from these containers", async () => {
    const user = userEvent.setup();
    render(
      <>
        <MessageList messages={[message("m1", "Hello")]} />
        <DataTable columns={columns} rows={[{ id: "a" }]} getRowKey={(r) => r.id} caption="Accounts list" />
        <button type="button">only stop</button>
      </>,
    );

    await user.tab();

    expect(screen.getByRole("button", { name: "only stop" })).toHaveFocus();
  });
});
