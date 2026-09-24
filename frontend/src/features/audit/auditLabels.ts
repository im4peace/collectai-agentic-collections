import type { AuditStage } from "../../api/auditTypes";

/** The six audit stages, in the fixed display order E9-S2 AC1/AC4 require
 * -- always rendered in this order, every stage always identified by this
 * real text label (never color/icon alone). */
export const STAGE_LABELS: Record<AuditStage, string> = {
  INPUT: "Input",
  AI_INTERPRETATION: "AI interpretation",
  PROPOSAL: "Proposal",
  RULE_VALIDATION: "Rule validation",
  HUMAN_DECISION: "Human decision",
  FINAL_STATE: "Final state",
};

export const STAGE_ORDER: readonly AuditStage[] = [
  "INPUT",
  "AI_INTERPRETATION",
  "PROPOSAL",
  "RULE_VALIDATION",
  "HUMAN_DECISION",
  "FINAL_STATE",
];
