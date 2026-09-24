import { useSyncExternalStore } from "react";

import type { Persona, SessionInfo } from "../api/types";

/**
 * Client-side mirror of the server's demo session (AC1). Deliberately not a
 * React Context: `api/client.ts` (layer below `features/*`) needs to read
 * the current persona/token synchronously outside a component tree to
 * build request headers, so this is a plain external store, exposed to
 * components through `useSession` (React 18 `useSyncExternalStore`).
 *
 * `sessionToken` is stored (never rendered) so `api/client.ts` can send it
 * as `X-Demo-Session` on CUSTOMER requests, mirroring `api/deps.py`'s
 * `_resolve_customer_session`, which is the only code path that reads it.
 */
export interface SessionState {
  persona: Persona;
  customerId: string | null;
  displayName: string;
  capabilities: string[];
  demoLabel: string;
  sessionToken: string | null;
  issuedAt: string;
}

const STORAGE_KEY = "collectai.demoSession";

function readPersisted(): SessionState | null {
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    return raw === null ? null : (JSON.parse(raw) as SessionState);
  } catch {
    return null;
  }
}

function writePersisted(state: SessionState | null): void {
  try {
    if (state === null) {
      window.sessionStorage.removeItem(STORAGE_KEY);
    } else {
      window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    }
  } catch {
    // sessionStorage unavailable (private mode, disabled storage): the
    // in-memory store still works for the current page load.
  }
}

let currentState: SessionState | null = readPersisted();
const listeners = new Set<() => void>();

function emitChange(): void {
  for (const listener of listeners) {
    listener();
  }
}

export function getSession(): SessionState | null {
  return currentState;
}

export function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function setSession(info: SessionInfo): void {
  currentState = {
    persona: info.persona,
    customerId: info.customer_id,
    displayName: info.display_name,
    capabilities: info.capabilities,
    demoLabel: info.demo_label,
    sessionToken: info.session_token ?? currentState?.sessionToken ?? null,
    issuedAt: info.issued_at,
  };
  writePersisted(currentState);
  emitChange();
}

export function clearSession(): void {
  currentState = null;
  writePersisted(null);
  emitChange();
}

export function useSession(): SessionState | null {
  return useSyncExternalStore(subscribe, getSession);
}
