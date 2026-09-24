/** Must equal the backend's `DEMO_LABEL`
 * (`backend/src/collectai/api/schemas/session.py`) so the UI never drifts
 * from what `SessionInfo.demo_label` actually says. */
export const DEMO_LABEL = "Demo persona - not real authentication";

/** AC4: the shell must always show this, visibly labelled as demo-only. */
export function DemoLabelChip(): JSX.Element {
  return <span className="chip demo">{DEMO_LABEL}</span>;
}
