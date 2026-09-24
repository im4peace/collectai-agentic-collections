export type BadgeVariant = "ok" | "warn" | "danger" | "info" | "neutral";

export interface BadgeProps {
  /** The visible text label. AC1 (E3-S3): a badge's meaning is never
   * carried by color alone, so callers always pass real text here, never
   * just a color. */
  text: string;
  variant: BadgeVariant;
  /** An optional decorative glyph (e.g. "▲"), rendered `aria-hidden`
   * since `text` alone already conveys the meaning to assistive tech. */
  icon?: string;
}

/**
 * Generic colored chip/badge (status, priority band, treatment flags, ...).
 * Not priority-band-specific: callers supply both the text and the variant,
 * so any later screen (Customer 360, Dashboard, Audit Trail) can reuse this
 * for its own labeled states.
 */
export function Badge({ text, variant, icon }: BadgeProps): JSX.Element {
  return (
    <span className={`chip ${variant}`}>
      {icon !== undefined && <span aria-hidden="true">{icon}</span>}
      {text}
    </span>
  );
}
