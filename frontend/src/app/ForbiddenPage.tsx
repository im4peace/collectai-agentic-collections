import { Link } from "react-router-dom";
import { SCREEN_TITLES, usePageTitle } from "../lib/pageTitle";

export interface ForbiddenPageProps {
  /** The resolved persona, or `null` when no demo session exists yet. */
  persona: string | null;
  /** The path that was denied. */
  route: string;
}

/**
 * AC3: shown instead of the requested screen when the current persona
 * lacks the capability a route requires. `role="alert"` so assistive
 * technology announces the denial immediately. Rendered by
 * `guards.tsx::RequireCapability` in place of the route's children, so the
 * data-fetching screen never mounts and never fires a request.
 */
export function ForbiddenPage({ persona, route }: ForbiddenPageProps): JSX.Element {
  usePageTitle(SCREEN_TITLES.forbidden);
  const personaLabel = persona ?? "No persona selected";
  return (
    <section className="forbidden" role="alert" aria-labelledby="forbidden-heading">
      <h1 id="forbidden-heading">403 - Forbidden</h1>
      <p>
        The persona <strong>{personaLabel}</strong> cannot open <code>{route}</code>.
      </p>
      <p>
        No restricted data was requested or rendered. The API would answer 403 FORBIDDEN and
        write an ACCESS_DENIED audit event.
      </p>
      <p>
        <Link to="/">Switch persona</Link>
      </p>
    </section>
  );
}
