import type { Kpi } from "../../api/kpiTypes";
import { formatMoney } from "../../components/MoneyText";

/** Mirrors `collectai_eval.reporting_rules.MIN_CASES_FOR_CLAIM` /
 * `kpi_service._MIN_CASES_FOR_CLAIM` (BRD 4.4, D-025): a per-category recall
 * claim needs at least this many labelled LIVE cases. The API already sets
 * `claim_status` accordingly; the UI re-applies the same rule so a tile can
 * never show a pass/fail-style figure for an under-sampled LIVE category
 * even if a payload were ever inconsistent (defence in depth). */
export const MIN_CASES_FOR_CLAIM = 30;

const RECALL_KPI_PREFIX = "sensitive_category_recall_";

function withThousandsSeparators(digits: string): string {
  return digits.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

/** `"1234"` -> `"1,234"`; a decimal tail is kept as-is (no rounding). */
export function formatCount(value: string): string {
  const [whole, fraction] = value.split(".");
  const grouped = withThousandsSeparators(whole);
  return fraction === undefined ? grouped : `${grouped}.${fraction}`;
}

/**
 * `"0.6120"` -> `"61.20%"`. Pure string arithmetic on the decimal (never a
 * float, so no binary-rounding artefact): the API quantizes ratios to four
 * decimals, i.e. exactly two decimals of a percent; anything longer is
 * truncated, never rounded up, so a displayed figure can never overstate.
 */
export function formatRatioAsPercent(value: string): string {
  const match = /^(\d+)(?:\.(\d+))?$/.exec(value);
  if (match === null) {
    return value;
  }
  const [, whole, fraction = ""] = match;
  const hundredths = BigInt(`${whole}${fraction.padEnd(4, "0").slice(0, 4)}`).toString();
  const padded = hundredths.padStart(3, "0");
  return `${padded.slice(0, -2)}.${padded.slice(-2)}%`;
}

/** Display form of a KPI's value by `unit`; `null` -> an explicit dash. */
export function formatKpiValue(kpi: Kpi): string {
  if (kpi.value === null) {
    return "-";
  }
  switch (kpi.unit) {
    case "COUNT":
      return formatCount(kpi.value);
    case "CURRENCY":
      return formatMoney(kpi.value);
    case "RATIO":
      return formatRatioAsPercent(kpi.value);
    case "MILLISECONDS":
      return `${formatCount(kpi.value)} ms`;
    case "USD_ESTIMATE":
      return `$${kpi.value} (estimate)`;
  }
}

/**
 * AC3: a LIVE tile is "observation only" when the API says so, *or* when it
 * is a per-category recall KPI with fewer than 30 labelled cases. Only LIVE
 * tiles can be observation-only in this sense: a MOCK tile is a regression
 * figure, never a claim, so it has nothing to withhold.
 */
export function isObservationOnly(kpi: Kpi): boolean {
  if (kpi.data_label !== "LIVE") {
    return false;
  }
  if (kpi.claim_status === "OBSERVATION_ONLY") {
    return true;
  }
  return (
    kpi.kpi_id.startsWith(RECALL_KPI_PREFIX) &&
    kpi.sample_size !== null &&
    kpi.sample_size < MIN_CASES_FOR_CLAIM
  );
}

/** Text shown next to a target, e.g. `"target 95.00%"`; ratios render as
 * percentages, everything else as the raw decimal string. */
export function formatTarget(kpi: Kpi): string | null {
  if (kpi.target === null) {
    return null;
  }
  return kpi.unit === "RATIO" ? formatRatioAsPercent(kpi.target) : kpi.target;
}
