# E4-S2 AC5: Customer 360 load performance benchmark

Generated: 2026-09-28T08:19:30.090Z

## Status summary

| | |
|---|---|
| Numerical target (p95 < 2,000 ms) | **FAIL** (p95 = 12755 ms) |
| BRD 10.6 Docker Compose environment requirement | **NOT VERIFIED** |
| Overall E4-S2 AC5 | **NOT MET by this measurement** |

BRD 10.6 (`specs/brd/brd.md`) requires this measurement to be "Measured
locally on Docker Compose". Docker was unavailable in the environment that
produced this run, so it was measured against the repository's documented
non-Docker Windows stack (README.md, "Running without Docker") instead. This
is a **NON-DOCKER OBSERVATIONAL MEASUREMENT**: it provides real evidence
about Customer 360 load performance on this hardware and data volume, but it
does **not** satisfy BRD 10.6's stated environment, and the numerical result
above must not be read as full BRD conformance. The same deviation was
already accepted, and disclosed the same way, for
`e3-s3-portfolio-perf-benchmark.md`.

## Method

30 scripted Playwright loads of `/customers/{accountId}` (via the persona
switcher, COLLECTIONS_OFFICER, then the Portfolio table's first row) after
one discarded warm-up run, against a database seeded with
`python -m collectai.bootstrap.cli seed --account-count 1000`.
"Interactive" is measured as navigation start to the Customer 360
DeterministicPanel's "Rules engine" heading becoming visible -- the panel
that renders Customer 360's core deterministic content (DPD, bucket,
overdue amount, priority band and factors; AC1), and only once
`GET /api/customers/{account_id}/360` has returned and been parsed (it sits
inside `Customer360Screen`'s `status === "loaded"` branch), so it cannot
fire before the primary data has finished loading. Single browser instance,
sequential runs (not parallelized, to avoid resource contention skewing the
measurement).

## Environment

- Measurement environment: **NON-DOCKER LOCAL STACK** (BRD 10.6 Docker Compose requirement: not verified by this run)
- `LLM_MODE`: MOCK
- Seeded accounts: 1000
- Warm-up runs (discarded): 1
- Measured runs: 30

## Hardware

- Platform: win32 10.0.26200
- CPU: 12th Gen Intel(R) Core(TM) i5-1235U (12 logical cores)
- Memory: 7.7 GiB total
- Node.js: v24.21.0

**Caveat:** this run was captured inside a sandboxed development
environment sharing CPU/memory with other processes (the backend API,
PostgreSQL, and the Vite dev server all on the same host), not dedicated
benchmark hardware, and not Docker Compose. Absolute numbers should be
treated as directional; see the status summary above.

## Results (ms)
- Run 1: 11583
- Run 2: 11669
- Run 3: 11607
- Run 4: 11594
- Run 5: 11642
- Run 6: 11636
- Run 7: 11709
- Run 8: 11678
- Run 9: 11669
- Run 10: 11745
- Run 11: 11654
- Run 12: 11686
- Run 13: 11644
- Run 14: 11630
- Run 15: 11639
- Run 16: 11086
- Run 17: 11639
- Run 18: 11592
- Run 19: 12600
- Run 20: 12099
- Run 21: 11800
- Run 22: 12755
- Run 23: 12722
- Run 24: 12718
- Run 25: 13136
- Run 26: 12100
- Run 27: 12126
- Run 28: 11586
- Run 29: 12291
- Run 30: 11180

## Summary
| Stat | Value (ms) |
|---|---|
| min | 11086 |
| p50 | 11669 |
| mean | 11874 |
| p95 | 12755 |
| max | 13136 |

**Numerical target: p95 < 2000 ms -- FAIL**
**BRD 10.6 Docker Compose environment requirement: NOT VERIFIED**
**Overall E4-S2 AC5: NOT MET by this measurement**
