import type { CSSProperties, ReactNode } from "react";
import { useEffect, useRef, useState } from "react";

/** True while `element`'s content overflows its box in either direction. */
function overflows(element: HTMLElement): boolean {
  return (
    element.scrollHeight > element.clientHeight + 1 || element.scrollWidth > element.clientWidth + 1
  );
}

/**
 * Tracks whether the referenced element currently scrolls. Re-measured when
 * the element or its first child is resized (a table's width follows its
 * content and the window) and when children are added or removed (a chat
 * transcript grows in place inside a fixed `max-height`).
 */
export function useIsScrollable(ref: React.RefObject<HTMLElement>): boolean {
  const [scrollable, setScrollable] = useState(false);

  useEffect(() => {
    const element = ref.current;
    if (element === null) return undefined;
    const measure = (): void => setScrollable(overflows(element));
    measure();

    const resizeObserver =
      typeof ResizeObserver === "undefined" ? null : new ResizeObserver(measure);
    resizeObserver?.observe(element);
    if (element.firstElementChild !== null) resizeObserver?.observe(element.firstElementChild);
    const mutationObserver =
      typeof MutationObserver === "undefined" ? null : new MutationObserver(measure);
    mutationObserver?.observe(element, { childList: true, subtree: true, characterData: true });
    window.addEventListener("resize", measure);

    return () => {
      resizeObserver?.disconnect();
      mutationObserver?.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, [ref]);

  return scrollable;
}

export interface ScrollRegionProps {
  /** The region's accessible name, e.g. "Conversation" or "Contributing factors". */
  label: string;
  className?: string;
  style?: CSSProperties;
  /** Keep the region role and name even while nothing overflows. For a primary
   * content area that is a landmark in its own right (the chat transcript);
   * tables leave it off so a non-scrolling table stays a plain wrapper. */
  alwaysNamed?: boolean;
  children: ReactNode;
}

/**
 * A container that may scroll (E11-S6 finding F-02, WCAG 2.1.1 Keyboard).
 * A scrollable box that cannot take focus leaves keyboard users unable to
 * scroll it, so while -- and only while -- its content overflows it becomes
 * `role="region"` with an accessible name and `tabIndex={0}`; browsers then
 * scroll it with the arrow, PageUp/PageDown, Home and End keys, and the
 * global `:focus-visible` outline shows where focus is. When nothing
 * overflows it adds no tab stop.
 */
export function ScrollRegion({
  label,
  className,
  style,
  alwaysNamed = false,
  children,
}: ScrollRegionProps): JSX.Element {
  const ref = useRef<HTMLDivElement>(null);
  const scrollable = useIsScrollable(ref);
  const named = scrollable || alwaysNamed;

  return (
    <div
      ref={ref}
      className={className}
      style={style}
      {...(named ? { role: "region", "aria-label": label } : {})}
      {...(scrollable ? { tabIndex: 0 } : {})}
    >
      {children}
    </div>
  );
}
