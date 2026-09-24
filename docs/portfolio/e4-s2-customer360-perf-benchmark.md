# E4-S2 AC5: Customer 360 load performance benchmark

Status: **deferred**, not fabricated. This entry exists so the target is
tracked rather than silently skipped.

## Target

AC5: Customer 360 main content interactive in under 2 s p95 over 30 scripted
Playwright loads after one warm-up run, mirroring E3-S3 AC5's own method
(see `docs/portfolio/e3-s3-portfolio-perf-benchmark.md`).

## Why this run is deferred, not measured

This story (Group G) was implemented without a running backend + Postgres +
Vite dev server stack available to the implementing session -- the same
constraint noted in the Group G handback: "do not attempt to run [Playwright
specs] yourself against a live stack -- that validation happens in a later
integration pass." Fabricating 30 timed runs without executing them would
misrepresent the measurement, which CLAUDE.md's engineering principles and
this codebase's own AC5 precedent (E3-S3's honestly-reported FAIL) both rule
out. The Playwright a11y specs and, when written, a perf spec mirroring
`frontend/e2e/perf/portfolio-load-benchmark.mjs`'s method should be run
against a live stack in the next integration pass, and this file updated
with real, timestamped results (pass or fail) exactly as
`e3-s3-portfolio-perf-benchmark.md` was -- never marked "passed" without a
captured run backing it.

## What is already true by construction

`GET /api/customers/{account_id}/360` is a single read-model assembly call
(`domain_services.customer360_service.build_customer360`) over already
-indexed repository reads and pure rules-engine computation, no AI call in
the request path -- structurally comparable in shape to the Portfolio
endpoint E3-S3 benchmarked, which suggests a similar order of magnitude
once measured, but that is an expectation, not a substitute for the
measurement AC5 actually requires.
