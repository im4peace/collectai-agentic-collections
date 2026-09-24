import type { ReactNode } from "react";
import { useEffect, useId, useRef } from "react";

export interface ConfirmDialogProps {
  isOpen: boolean;
  title: string;
  /** Called on Cancel, Escape, or the overlay/close action -- always the
   * "give up and go back to what I was doing" path. */
  onClose: () => void;
  /** Omitted for a dialog that is informational only (no destructive/
   * confirming action, just a close button). */
  onConfirm?: () => void;
  confirmLabel?: string;
  cancelLabel?: string;
  confirmDisabled?: boolean;
  /** True while an async confirm/cancel is in flight: disables both
   * buttons so a second click cannot fire a second request. */
  busy?: boolean;
  children: ReactNode;
}

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

function focusableElements(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR));
}

/**
 * Generic modal dialog (title, body, Cancel/optional Confirm), reused by
 * both Customer 360's "Record Promise-to-Pay" form and the Chat screen's
 * proposal Confirm/Cancel UI (E4-S2 AC7, E6-S5 AC7). Implements focus
 * management by hand (a plain `role="dialog"` overlay, not the native
 * `<dialog>` element) so the same behaviour is exercised identically by
 * Vitest/jsdom unit tests and real browsers: on open, focus moves into the
 * dialog; while open, Tab/Shift+Tab cycles within it; on close, focus
 * returns to whatever was focused before it opened.
 */
export function ConfirmDialog({
  isOpen,
  title,
  onClose,
  onConfirm,
  confirmLabel,
  cancelLabel,
  confirmDisabled,
  busy,
  children,
}: ConfirmDialogProps): JSX.Element | null {
  const dialogRef = useRef<HTMLDivElement>(null);
  const previouslyFocused = useRef<HTMLElement | null>(null);
  const titleId = useId();

  useEffect(() => {
    if (!isOpen) {
      return undefined;
    }
    previouslyFocused.current =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const dialogEl = dialogRef.current;
    const [firstFocusable] = dialogEl ? focusableElements(dialogEl) : [];
    (firstFocusable ?? dialogEl)?.focus();
    return () => {
      previouslyFocused.current?.focus();
    };
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) {
      return undefined;
    }
    function handleKeyDown(event: KeyboardEvent): void {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab") {
        return;
      }
      const dialogEl = dialogRef.current;
      const focusable = dialogEl ? focusableElements(dialogEl) : [];
      if (focusable.length === 0) {
        event.preventDefault();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) {
    return null;
  }

  return (
    <div className="dialog-overlay">
      <div className="dialog" role="dialog" aria-modal="true" aria-labelledby={titleId} ref={dialogRef} tabIndex={-1}>
        <h2 id={titleId}>{title}</h2>
        <div className="dialog-body">{children}</div>
        <div className="dialog-actions row">
          <button type="button" className="btn secondary" onClick={onClose} disabled={busy}>
            {cancelLabel ?? "Cancel"}
          </button>
          {onConfirm && (
            <button type="button" className="btn" onClick={onConfirm} disabled={confirmDisabled === true || busy === true}>
              {confirmLabel ?? "Confirm"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
