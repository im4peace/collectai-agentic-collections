import { Badge } from "../../components/Badge";
import { SCREEN_TITLES, usePageTitle } from "../../lib/pageTitle";
import { AdvanceClockPanel } from "./AdvanceClockPanel";
import { DemoStatePanel } from "./DemoStatePanel";
import { PtpLifecyclePanel } from "./PtpLifecyclePanel";
import { ReseedPanel } from "./ReseedPanel";
import { SimulatePaymentPanel } from "./SimulatePaymentPanel";
import { useDemoState } from "./useDemoState";

/**
 * E9-S3 (BRD 14.1 screen 8): the dev and demo controls. Reachable only
 * through `RequireCapability capability="demo_controls:use"` in
 * `app/router.tsx` (COLLECTIONS_OFFICER), so any other persona never mounts
 * this component and never fires a request.
 *
 * The API flag `DEMO_CONTROLS_ENABLED` is off by default, and then every demo
 * route answers 404. AC1: with the flag off no control is rendered at all,
 * only a plain explanation. With it on, the screen shows the AI mode as
 * text and the four controls. Opening the screen sends a single GET; nothing
 * here writes anything until a person submits a form.
 */
export function DemoControlsScreen(): JSX.Element {
  usePageTitle(SCREEN_TITLES.demoControls);
  const { status, state, errorMessage, reload, retry } = useDemoState();

  return (
    <div className="pagehead-wrap">
      <div className="pagehead">
        <div>
          <h1>Demo controls</h1>
          <p className="muted">
            For demos and development only. Disabled by default and never part of a production
            path. These controls change shared demo state.
          </p>
        </div>
        <Badge text="Demo only" variant="warn" icon="⚠" />
      </div>

      {status === "loading" && (
        <p role="status" aria-live="polite">
          Loading demo controls&hellip;
        </p>
      )}

      {status === "disabled" && (
        <section className="panel" role="status" aria-labelledby="demo-off-heading">
          <h2 id="demo-off-heading">Demo controls are turned off</h2>
          <p>
            The API answered 404 for the demo-control routes, so they are disabled and no control
            is shown. To turn them on, set <code>DEMO_CONTROLS_ENABLED=true</code> for the API and
            restart it.
          </p>
        </section>
      )}

      {status === "error" && (
        <div className="banner danger" role="alert">
          <div>{errorMessage ?? "Could not load the demo controls."}</div>
          <button type="button" className="btn secondary" onClick={retry}>
            Retry
          </button>
        </div>
      )}

      {status === "ready" && state !== null && (
        <div className="checks" style={{ flexDirection: "column", alignItems: "stretch", gap: 12 }}>
          <DemoStatePanel state={state} />
          <AdvanceClockPanel onChanged={reload} />
          <PtpLifecyclePanel />
          <SimulatePaymentPanel />
          <ReseedPanel onChanged={reload} />
        </div>
      )}
    </div>
  );
}
