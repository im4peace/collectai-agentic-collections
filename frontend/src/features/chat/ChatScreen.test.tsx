import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as chatClient from "../../api/chatClient";
import * as meClient from "../../api/meClient";
import type {
  ChatTurnResponse,
  ConversationCreateResult,
  HandoffResult,
  Proposal,
} from "../../api/chatTypes";
import type { CustomerAccountPage } from "../../api/meTypes";
import { ChatScreen } from "./ChatScreen";

vi.mock("../../api/chatClient", () => ({
  createConversation: vi.fn(),
  sendMessage: vi.fn(),
  confirmProposal: vi.fn(),
  cancelProposal: vi.fn(),
  requestHandoff: vi.fn(),
}));
vi.mock("../../api/meClient", () => ({ getMyAccounts: vi.fn() }));

const ACCOUNTS: CustomerAccountPage = {
  items: [
    {
      account_id: "acc_000123",
      account_type: "CARD",
      product_name: "Everyday Rewards Card",
      currency: "AED",
      outstanding_balance: "4820.35",
      overdue_amount: "612.40",
      collection_status: "IN_PROGRESS",
    },
  ],
  page: { limit: 20, offset: 0, total: 1 },
};

const GREETING: ConversationCreateResult = {
  conversation: {
    conversation_id: "conv_01J8ZK4A9B",
    account_id: "acc_000123",
    status: "ACTIVE",
    created_at: "2026-10-01T14:00:00Z",
    last_message_at: "2026-10-01T14:00:00Z",
  },
  greeting: {
    message_id: "msg_1",
    conversation_id: "conv_01J8ZK4A9B",
    role: "ASSISTANT",
    content: "Hi, I'm an AI assistant here to help with your account.",
    content_source: "TEMPLATE",
    labels: ["AI_DISCLOSURE"],
    created_at: "2026-10-01T14:00:00Z",
  },
  talk_to_human_available: true,
};

function baseProposal(overrides: Partial<Proposal> = {}): Proposal {
  const base: Proposal = {
    proposal_id: "prp_01J8ZK5B00",
    conversation_id: "conv_01J8ZK4A9B",
    kind: "PTP",
    status: "PENDING_CONFIRMATION",
    terms: { kind: "PTP", promised_amount: "250.00", promised_date: "2026-10-15" },
    terms_hash: "hash123",
    summary: "Promise to pay AED 250.00 by 2026-10-15.",
    simulated: false,
    record_version: 1,
    created_at: "2026-10-01T14:05:00Z",
    expires_at: "2026-10-01T14:35:00Z",
  };
  return { ...base, ...overrides };
}

async function renderReadyScreen() {
  vi.mocked(meClient.getMyAccounts).mockResolvedValue(ACCOUNTS);
  vi.mocked(chatClient.createConversation).mockResolvedValue(GREETING);
  const utils = render(<ChatScreen />);
  // The greeting appears twice by design: once in the visible message list,
  // once in the `LiveRegion` announcement (AC7) -- wait for both rather
  // than asserting a single unique match.
  await waitFor(() => expect(screen.getAllByText(GREETING.greeting.content).length).toBe(2));
  return utils;
}

describe("ChatScreen", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("opens with an AI disclosure message and keeps 'Talk to a human' visible (AC1)", async () => {
    await renderReadyScreen();

    expect(screen.getAllByText(GREETING.greeting.content).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Talk to a human" })).toBeInTheDocument();
  });

  it("clicking 'Talk to a human' creates an escalation and shows the follow-up message (AC2)", async () => {
    await renderReadyScreen();
    const user = userEvent.setup();

    const handoffResult: HandoffResult = {
      escalation: {
        case_id: "esc_01J8ZK6E1A",
        account_id: "acc_000123",
        status: "OPEN",
        customer_message: "Thanks for reaching out. A human colleague will follow up with you shortly.",
        created_at: "2026-10-01T14:06:00Z",
        decided_at: null,
      },
      assistant_message: {
        message_id: "msg_2",
        conversation_id: "conv_01J8ZK4A9B",
        role: "ASSISTANT",
        content: "A human colleague will follow up with you shortly.",
        content_source: "TEMPLATE",
        labels: ["HUMAN_HANDOFF"],
        created_at: "2026-10-01T14:06:00Z",
      },
      replayed: false,
    };
    vi.mocked(chatClient.requestHandoff).mockResolvedValue(handoffResult);

    await user.click(screen.getByRole("button", { name: "Talk to a human" }));

    await waitFor(() => expect(chatClient.requestHandoff).toHaveBeenCalled());
    expect(await screen.findByText(handoffResult.escalation.customer_message)).toBeInTheDocument();
  });

  it("shows Confirm and Cancel for a pending proposal, and Confirm submits nothing until clicked (AC3)", async () => {
    await renderReadyScreen();
    const user = userEvent.setup();

    const turn: ChatTurnResponse = {
      conversation_id: "conv_01J8ZK4A9B",
      turn_id: "trn_1",
      customer_message: {
        message_id: "msg_3",
        conversation_id: "conv_01J8ZK4A9B",
        role: "CUSTOMER",
        content: "I can pay 250 by the 15th",
        content_source: "CUSTOMER_INPUT",
        labels: [],
        created_at: "2026-10-01T14:05:00Z",
      },
      assistant_message: {
        message_id: "msg_4",
        conversation_id: "conv_01J8ZK4A9B",
        role: "ASSISTANT",
        content: "Here's what I can offer:",
        content_source: "TEMPLATE",
        labels: [],
        created_at: "2026-10-01T14:05:01Z",
      },
      intent: null,
      proposal: baseProposal(),
      handoff: null,
      safe_state: "NONE",
      talk_to_human_available: true,
      correlation_id: "corr-1",
      escalation_reported: false,
      escalation_reason: null,
    };
    vi.mocked(chatClient.sendMessage).mockResolvedValue(turn);
    vi.mocked(chatClient.confirmProposal).mockResolvedValue({
      proposal: null,
      outcome: { kind: "PTP", ptp: null, payment_event: null, arrangement: null, escalation: null },
      assistant_message: {
        message_id: "msg_7",
        conversation_id: "conv_01J8ZK4A9B",
        role: "ASSISTANT",
        content: "Your promise to pay has been recorded.",
        content_source: "TEMPLATE",
        labels: [],
        created_at: "2026-10-01T14:05:05Z",
      },
      replayed: false,
    });

    await user.type(screen.getByLabelText("Message"), "I can pay 250 by the 15th");
    await user.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByRole("button", { name: "Confirm" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument();
    expect(chatClient.confirmProposal).not.toHaveBeenCalled();

    // Clicking "Confirm" opens a dialog -- nothing is submitted until that
    // dialog's own confirm action is clicked (AC3, AC7's focus-trapped step).
    await user.click(screen.getByRole("button", { name: "Confirm" }));
    expect(chatClient.confirmProposal).not.toHaveBeenCalled();

    const dialogConfirm = screen.getByRole("dialog").querySelector("button.btn:not(.secondary)");
    expect(dialogConfirm).not.toBeNull();
    await user.click(dialogConfirm as HTMLButtonElement);

    await waitFor(() =>
      expect(chatClient.confirmProposal).toHaveBeenCalledWith(
        "conv_01J8ZK4A9B",
        "prp_01J8ZK5B00",
        "hash123",
        expect.any(String),
      ),
    );
  });

  it("shows a visible 'Simulated payment' label for a payment proposal (AC4)", async () => {
    await renderReadyScreen();
    const user = userEvent.setup();

    const paymentProposal = baseProposal({
      kind: "PAYMENT",
      simulated: true,
      terms: {
        kind: "PAYMENT",
        payment_option: "OVERDUE_AMOUNT",
        payment_amount: "612.40",
        simulated: true,
        simulated_label: "Simulated payment",
      },
      summary: "Simulated payment of your overdue amount, AED 612.40.",
    });
    const turn: ChatTurnResponse = {
      conversation_id: "conv_01J8ZK4A9B",
      turn_id: "trn_2",
      customer_message: {
        message_id: "msg_5",
        conversation_id: "conv_01J8ZK4A9B",
        role: "CUSTOMER",
        content: "pay now",
        content_source: "CUSTOMER_INPUT",
        labels: [],
        created_at: "2026-10-01T14:07:00Z",
      },
      assistant_message: {
        message_id: "msg_6",
        conversation_id: "conv_01J8ZK4A9B",
        role: "ASSISTANT",
        content: "Confirm the simulated payment below.",
        content_source: "TEMPLATE",
        labels: [],
        created_at: "2026-10-01T14:07:01Z",
      },
      intent: null,
      proposal: paymentProposal,
      handoff: null,
      safe_state: "NONE",
      talk_to_human_available: true,
      correlation_id: "corr-2",
      escalation_reported: false,
      escalation_reason: null,
    };
    vi.mocked(chatClient.sendMessage).mockResolvedValue(turn);

    await user.type(screen.getByLabelText("Message"), "pay now");
    await user.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByText("Simulated payment")).toBeInTheDocument();
  });

  it("shows a safe error and keeps 'Talk to a human' available when the handoff fails (AC6)", async () => {
    await renderReadyScreen();
    const user = userEvent.setup();

    const { ApiError } = await import("../../api/errors");
    vi.mocked(chatClient.requestHandoff).mockRejectedValue(
      new ApiError(503, {
        code: "AUDIT_UNAVAILABLE",
        reason_code: null,
        message: "The handoff could not be completed. Please try again.",
        correlation_id: "corr-3",
        details: [],
        alternatives: null,
        context: null,
      }),
    );

    await user.click(screen.getByRole("button", { name: "Talk to a human" }));

    expect(await screen.findByText(/handoff could not be completed/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Talk to a human" })).toBeInTheDocument();
  });
});
