/**
 * Placeholder root component (E1-S5). Proves the SPA builds, runs and
 * tests end to end. Routing, layouts, the persona switcher and every real
 * screen are added by later UI stories (E3-S3 onward) per
 * `specs/design/folder-structure.md`'s `frontend/src/` tree — this
 * component is deliberately not extended ahead of those stories.
 */
export function App(): JSX.Element {
  return (
    <main>
      <h1>CollectAI</h1>
      <p>AI-native Collections &amp; Recovery platform (portfolio demo, synthetic data only).</p>
    </main>
  );
}
