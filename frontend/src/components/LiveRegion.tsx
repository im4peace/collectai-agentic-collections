export interface LiveRegionProps {
  /** The text to announce -- typically the latest assistant message. An
   * unchanged value announces nothing again (browsers only announce an
   * `aria-live` region's content on a real text change). */
  message: string;
}

/**
 * Visually hidden, polite live region (E6-S5 AC7): announces new assistant
 * messages to assistive technology without interrupting whatever the
 * customer is doing. Generic on purpose (just renders whatever `message` it
 * is given) so any screen with an announce-on-change need can reuse it.
 */
export function LiveRegion({ message }: LiveRegionProps): JSX.Element {
  return (
    <div className="sr" aria-live="polite" role="status">
      {message}
    </div>
  );
}
