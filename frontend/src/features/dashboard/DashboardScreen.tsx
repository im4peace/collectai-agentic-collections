import type { Kpi } from "../../api/kpiTypes";
import { Badge } from "../../components/Badge";
import { formatDateTime } from "../../lib/formatDateTime";
import { EvalRunsTable } from "./EvalRunsTable";
import { KpiTile } from "./KpiTile";
import { useKpiQuery } from "./useKpiQuery";
import { SCREEN_TITLES, usePageTitle } from "../../lib/pageTitle";

function TileGrid({ kpis, headingLevel }: { kpis: Kpi[]; headingLevel: 3 | 4 }): JSX.Element {
  return (
    <div className="tiles">
      {kpis.map((kpi) => (
        <KpiTile key={kpi.kpi_id} kpi={kpi} headingLevel={headingLevel} />
      ))}
    </div>
  );
}

function EmptyNote({ children }: { children: string }): JSX.Element {
  return (
    <div className="empty" role="status">
      {children}
    </div>
  );
}

/**
 * E10-S4: the manager dashboard. Strictly read-only (AC4): it renders the
 * `GET /api/kpis` tree as three headed sections and has no control that
 * writes anything (the only button, Retry, re-reads). Reachable only through
 * `RequireCapability capability="kpi:read"` in `app/router.tsx` (AC5), so a
 * forbidden persona never mounts this component and never fetches KPI data.
 * MOCK and LIVE AI figures are always in separate tiles (AC2), and there is
 * no LIVE run to show until one is stored -- the empty state says so plainly
 * rather than filling it with MOCK numbers (BRD 4.6).
 */
export function DashboardScreen(): JSX.Element {
  usePageTitle(SCREEN_TITLES.dashboard);
  const { status, data, errorMessage, evalRuns, refetch } = useKpiQuery();

  return (
    <div className="pagehead-wrap">
      <div className="pagehead">
        <div>
          <h1>Collections and AI performance</h1>
          <p className="muted">
            Read-only. Every figure carries a label: ILLUSTRATIVE (synthetic business data), MOCK
            (scripted provider) or LIVE (real model runs).
          </p>
        </div>
        <Badge text="Read-only" variant="neutral" icon="▣" />
      </div>

      {status === "loading" && (
        <p role="status" aria-live="polite">
          Loading KPIs&hellip;
        </p>
      )}

      {status === "error" && (
        <div className="banner danger" role="alert">
          <div>
            <strong>The KPI data could not be loaded. No figures are shown.</strong>
            <br />
            {errorMessage}
          </div>
          <button type="button" className="btn secondary" onClick={refetch}>
            Retry
          </button>
        </div>
      )}

      {status === "loaded" && data !== null && (
        <>
          <nav className="row small" aria-label="Jump to section">
            <span className="muted">Jump to:</span>
            <a href="#kpi-business">Business</a>
            <a href="#kpi-operational">Operational</a>
            <a href="#kpi-ai">AI quality and governance</a>
          </nav>
          <p className="small muted">
            Generated {formatDateTime(data.generated_at)} &middot; policy_version{" "}
            {data.policy_version ?? "unavailable"}
          </p>

          <section className="sec" id="kpi-business" aria-labelledby="kpi-business-heading">
            <h2 id="kpi-business-heading">Business</h2>
            <p className="small muted">
              Illustrative figures from synthetic data. They show what the dashboard would track,
              not real performance.
            </p>
            <TileGrid kpis={data.business} headingLevel={3} />
          </section>

          <section className="sec" id="kpi-operational" aria-labelledby="kpi-operational-heading">
            <h2 id="kpi-operational-heading">Operational</h2>
            <TileGrid kpis={data.operational} headingLevel={3} />
          </section>

          <section className="sec" id="kpi-ai" aria-labelledby="kpi-ai-heading">
            <h2 id="kpi-ai-heading">AI quality and governance</h2>
            <div className="banner info">
              <div>{data.ai_quality.note}</div>
            </div>

            <h3>MOCK regression results</h3>
            <p className="small muted">Scripted provider. Not compared to targets.</p>
            {data.ai_quality.mock.length > 0 ? (
              <TileGrid kpis={data.ai_quality.mock} headingLevel={4} />
            ) : (
              <EmptyNote>No MOCK evaluation run stored yet.</EmptyNote>
            )}

            <h3>LIVE evaluation results</h3>
            {data.ai_quality.live_run_available && data.ai_quality.live.length > 0 ? (
              <TileGrid kpis={data.ai_quality.live} headingLevel={4} />
            ) : (
              <div className="empty" role="status">
                <strong>No LIVE run</strong>
                <p>
                  No LIVE evaluation run has been stored. Nothing is estimated or copied from MOCK
                  results.
                </p>
              </div>
            )}

            {evalRuns !== null && (
              <>
                <h3>Stored evaluation runs</h3>
                <EvalRunsTable runs={evalRuns} />
              </>
            )}
          </section>

          <p className="footnote">
            This dashboard has no controls that change data. Figures are system-calculated from
            stored records; no AI produces them.
          </p>
        </>
      )}
    </div>
  );
}
