export interface RouteStubProps {
  title: string;
}

/**
 * Placeholder for a guarded route slot this story wires up but does not
 * build the real screen for (E3-S3 and later Group G/H stories fill these
 * in). Reachable only once `RequireCapability` has already allowed the
 * route, so a stub never renders for a persona that should be forbidden.
 */
export function RouteStub({ title }: RouteStubProps): JSX.Element {
  return (
    <div>
      <h1>{title}</h1>
      <p>Coming soon.</p>
    </div>
  );
}
