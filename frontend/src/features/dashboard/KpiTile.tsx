import type { Kpi } from "../../api/kpiTypes";
import { Badge } from "../../components/Badge";
import type { BadgeVariant } from "../../components/Badge";
import {
  MIN_CASES_FOR_CLAIM,
  formatCount,
  formatKpiValue,
  formatTarget,
  isObservationOnly,
} from "./kpiFormat";

const LABEL_VARIANT: Record<Kpi["data_label"], BadgeVariant> = {
  ILLUSTRATIVE: "neutral",
  MOCK: "warn",
  LIVE: "ok",
};

const LABEL_ICON: Record<Kpi["data_label"], string> = {
  ILLUSTRATIVE: "◌",
  MOCK: "◇",
  LIVE: "●",
};

const LABEL_CLASS: Record<Kpi["data_label"], string> = {
  ILLUSTRATIVE: "ill",
  MOCK: "mock",
  LIVE: "live",
};

export interface KpiTileProps {
  kpi: Kpi;
  /** Heading level of the tile's name: 3 under a section `<h2>`, 4 under an
   * AI-section `<h3>` subheading, so the outline never skips a level. */
  headingLevel: 3 | 4;
}

/** The one line under the headline value: "N of M" for ratio KPIs, else the
 * sample size. Never a percentage, so it is safe on an observation-only tile. */
function supportingText(kpi: Kpi): string {
  if (kpi.numerator !== null && kpi.denominator !== null) {
    return `${formatCount(kpi.numerator)} of ${formatCount(kpi.denominator)}`;
  }
  return kpi.sample_size !== null ? `sample ${formatCount(String(kpi.sample_size))}` : "";
}

/** Why an observation-only tile withholds a claim, in words. */
function observationNote(kpi: Kpi): string {
  if (kpi.sample_size !== null && kpi.sample_size < MIN_CASES_FOR_CLAIM) {
    return ` (fewer than ${MIN_CASES_FOR_CLAIM} labelled LIVE cases; no pass or fail is shown)`;
  }
  return " (no pass or fail is shown)";
}

function ClaimIndicator({ kpi }: { kpi: Kpi }): JSX.Element | null {
  if (isObservationOnly(kpi)) {
    return <Badge text="observation only" variant="warn" icon="◎" />;
  }
  if (kpi.data_label !== "LIVE") {
    return null;
  }
  const target = formatTarget(kpi);
  if (kpi.claim_status === "PASS") {
    return <Badge text={`PASS vs target ${target ?? ""}`.trim()} variant="ok" icon="✔" />;
  }
  if (kpi.claim_status === "FAIL") {
    return <Badge text={`FAIL vs target ${target ?? ""}`.trim()} variant="danger" icon="✖" />;
  }
  return null;
}

/**
 * One read-only KPI tile (E10-S4 AC2, AC3). The data label is always real
 * text (ILLUSTRATIVE / MOCK / LIVE), never colour alone. An observation-only
 * LIVE tile replaces the headline percentage with the words "Observation
 * only" and shows no pass/fail indicator; a MOCK tile shows its figure as a
 * regression check and never a pass/fail claim (BRD 4.6).
 */
export function KpiTile({ kpi, headingLevel }: KpiTileProps): JSX.Element {
  const Heading = headingLevel === 3 ? "h3" : "h4";
  const headingId = `kpi-${kpi.kpi_id}-name`;
  const observationOnly = isObservationOnly(kpi);
  const target = formatTarget(kpi);
  const supporting = supportingText(kpi);

  return (
    <article
      className={`tile ${LABEL_CLASS[kpi.data_label]}`}
      data-kpi={kpi.kpi_id}
      aria-labelledby={headingId}
    >
      <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
        <Heading id={headingId} className="tile-name">
          {kpi.name}
        </Heading>
        <Badge text={kpi.data_label} variant={LABEL_VARIANT[kpi.data_label]} icon={LABEL_ICON[kpi.data_label]} />
      </div>
      <div className="v">{observationOnly ? "Observation only" : formatKpiValue(kpi)}</div>
      {(supporting !== "" || observationOnly) && (
        <div className="small muted">
          {supporting}
          {observationOnly && observationNote(kpi)}
        </div>
      )}
      {kpi.data_label === "MOCK" && (
        <div className="small muted">Regression check only. Not evidence of model quality.</div>
      )}
      <div>
        <ClaimIndicator kpi={kpi} />
      </div>
      {target !== null && kpi.claim_status === "NOT_APPLICABLE" && (
        <span className="small muted">Target (observational): {target}</span>
      )}
      <details>
        <summary>Definition and formula</summary>
        <dl className="small kpi-details">
          <dt>Definition</dt>
          <dd>{kpi.definition}</dd>
          <dt>Formula</dt>
          <dd>
            <code>{kpi.formula}</code>
          </dd>
          <dt>Owner</dt>
          <dd>{kpi.owner_persona}</dd>
          <dt>Source</dt>
          <dd>{kpi.source_note ?? "-"}</dd>
        </dl>
      </details>
    </article>
  );
}
