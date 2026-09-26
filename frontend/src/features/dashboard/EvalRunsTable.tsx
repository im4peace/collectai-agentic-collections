import type { EvalRunSummary } from "../../api/kpiTypes";
import { Badge } from "../../components/Badge";
import { formatDateTime } from "../../lib/formatDateTime";
import { formatRatioAsPercent } from "./kpiFormat";

export interface EvalRunsTableProps {
  runs: EvalRunSummary[];
}

/** The stored evaluation runs behind the AI tiles, each row carrying its own
 * MOCK/LIVE text label so the two are never read as one series (BRD 4.6).
 * Read-only. */
export function EvalRunsTable({ runs }: EvalRunsTableProps): JSX.Element {
  if (runs.length === 0) {
    return (
      <div className="empty" role="status">
        No stored evaluation runs.
      </div>
    );
  }
  return (
    <div className="tablewrap">
      <table>
        <caption className="sr">Stored evaluation runs, newest first</caption>
        <thead>
          <tr>
            <th scope="col">Run</th>
            <th scope="col">Data label</th>
            <th scope="col">Dataset</th>
            <th scope="col">Model / prompt / policy</th>
            <th scope="col" className="num">
              Cases
            </th>
            <th scope="col" className="num">
              Intent accuracy
            </th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <tr key={run.eval_run_id}>
              <td className="mono small">
                {run.eval_run_id}
                <br />
                {formatDateTime(run.run_at)}
              </td>
              <td>
                <Badge text={run.mode} variant={run.mode === "LIVE" ? "ok" : "warn"} />
              </td>
              <td>{run.dataset_version}</td>
              <td className="small">
                {run.model_id ?? "(no model)"}
                <br />
                {run.prompt_version} / {run.policy_version}
              </td>
              <td className="num">{run.case_count}</td>
              <td className="num">
                {run.intent_accuracy === null ? "-" : formatRatioAsPercent(run.intent_accuracy)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
