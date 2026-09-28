# E3-S3 AC5: Portfolio load performance benchmark

Generated: 2026-09-23T16:46:47.396Z

## Status summary

| | |
|---|---|
| Numerical target (p95 < 2,000 ms) | **FAIL** (p95 = 17496 ms) |
| BRD 10.6 Docker Compose environment requirement | **NOT VERIFIED** |
| Overall E3-S3 AC5 | **NOT MET by this measurement** |

BRD 10.6 (`specs/brd/brd.md`) requires this measurement to be "Measured
locally on Docker Compose". This run's own caveat below (backend API,
PostgreSQL and the Vite dev server sharing one host) describes the
repository's documented non-Docker stack, not `docker compose up`; this run
was not run or labelled as Docker Compose at the time, so that requirement
is recorded here as **NOT VERIFIED** rather than assumed either way. This
remains valid observational evidence for the environment it was actually
captured on, but it does not establish performance on the BRD-prescribed
Docker Compose environment, and it must not be read as an inference that the
application cannot meet the target once measured there. Docker Compose
remeasurement remains required for environment-conformant verification (see
decision `PERF-001`, `decision-log.md`).

## Method
30 scripted Playwright loads of `/portfolio` (via the persona switcher,
COLLECTIONS_OFFICER) after one discarded warm-up run, against a database
seeded with `python -m collectai.bootstrap.cli seed --account-count 1000`.
"Interactive" is measured as navigation start to the Portfolio table
becoming visible. Single browser instance, sequential runs (not
parallelized, to avoid resource contention skewing the measurement).

## Hardware
- Platform: win32 10.0.26200
- CPU: 12th Gen Intel(R) Core(TM) i5-1235U (12 logical cores)
- Memory: 7.7 GiB total

**Caveat:** this run was captured inside a sandboxed development
environment sharing CPU/memory with other processes (the backend API,
PostgreSQL, and the Vite dev server all on the same host), not dedicated
benchmark hardware. Absolute numbers should be treated as directional; see
the note in the report's summary.

## Results (ms)
- Run 1: 10389
- Run 2: 10397
- Run 3: 10377
- Run 4: 9868
- Run 5: 10198
- Run 6: 8722
- Run 7: 8730
- Run 8: 9352
- Run 9: 8731
- Run 10: 8840
- Run 11: 9234
- Run 12: 9252
- Run 13: 19071
- Run 14: 17496
- Run 15: 17404
- Run 16: 17440
- Run 17: 16909
- Run 18: 16911
- Run 19: 17459
- Run 20: 17010
- Run 21: 17067
- Run 22: 15893
- Run 23: 7146
- Run 24: 6632
- Run 25: 6634
- Run 26: 6641
- Run 27: 6640
- Run 28: 6641
- Run 29: 6623
- Run 30: 6637

## Summary
| Stat | Value (ms) |
|---|---|
| min | 6623 |
| p50 | 9352 |
| mean | 11345 |
| p95 | 17496 |
| max | 19071 |

**AC5 target: p95 < 2000 ms -- FAIL**
**BRD 10.6 Docker Compose environment requirement: NOT VERIFIED**
**Overall E3-S3 AC5: NOT MET by this measurement**
