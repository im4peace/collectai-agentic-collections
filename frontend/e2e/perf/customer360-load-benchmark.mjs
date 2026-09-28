// E4-S2 AC5 performance benchmark: "Customer 360 main content is interactive
// in under 2 s p95 over 30 scripted loads after one warm-up." Methodology
// mirrors e2e/perf/portfolio-load-benchmark.mjs (E3-S3 AC5) exactly: a
// **manually triggered** script (not part of `make test`/CI, since CI
// runners are not representative hardware), 30 runs after one warm-up,
// 1,000-account seed, hardware recorded, result committed to
// `docs/portfolio/`.
//
// Completion marker: `getByRole("heading", { name: "Rules engine" })`, the
// DeterministicPanel's own `<h2>` (data.deterministic.label, the backend's
// own AC2 string). It renders only inside Customer360Screen's
// `status === "loaded" && data !== null` branch -- i.e. only after
// `GET /api/customers/{account_id}/360` has returned and been parsed -- so
// it cannot appear before the primary Customer 360 data has finished
// loading, unlike the page heading ("Customer 360", always present) or the
// "Loading customer record..." status text (present *before* data arrives).
// It is also the same selector the existing accessibility spec
// (e2e/accessibility/customer360.spec.ts) already uses as a load-complete
// signal, so it is a proven-stable pre-existing marker. No production code
// was changed to add this marker.
//
// BRD 10.6 says this measurement is "Measured locally on Docker Compose".
// This script has no Docker-specific logic and does not verify or assume
// Docker; it only needs a reachable frontend and API, whichever way they
// were started. Environment conformance is recorded in the generated report
// (and must be read there), not decided by this script.
//
// Usage (from `frontend/`, with the backend API and `npm run dev` already
// running against a database seeded with `--account-count 1000`):
//   node e2e/perf/customer360-load-benchmark.mjs [baseURL]
//
// Not a `*.spec.ts` file on purpose: Playwright's default `testMatch` never
// picks this up, so it never runs as part of `npx playwright test` / CI's
// `e2e` job -- only when explicitly invoked, per deployment.md.

import { chromium } from "@playwright/test";
import { writeFileSync, mkdirSync } from "node:fs";
import { cpus, totalmem, platform, release } from "node:os";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const RUN_COUNT = 30;
const ACCOUNT_COUNT = 1000;
const LLM_MODE = process.env.LLM_MODE ?? "MOCK";
const MEASUREMENT_ENVIRONMENT = "NON-DOCKER LOCAL STACK";
const BASE_URL = process.argv[2] ?? "http://localhost:5173";
const __dirname = dirname(fileURLToPath(import.meta.url));
const REPORT_DIR = join(__dirname, "..", "..", "..", "docs", "portfolio");

async function loadCustomer360Once(browser) {
  const page = await browser.newPage();
  const start = Date.now();
  await page.goto(BASE_URL + "/");
  await page.getByRole("radio", { name: /COLLECTIONS_OFFICER/ }).click();
  await page.getByRole("button", { name: "Use this persona" }).click();
  await page.getByRole("table").waitFor({ state: "visible" });
  await page.locator("tbody tr").first().getByRole("link").click();
  await page.getByRole("heading", { name: "Rules engine" }).waitFor({ state: "visible" });
  const elapsedMs = Date.now() - start;
  await page.close();
  return elapsedMs;
}

function percentile(sorted, p) {
  const index = Math.min(sorted.length - 1, Math.ceil((p / 100) * sorted.length) - 1);
  return sorted[Math.max(0, index)];
}

async function main() {
  console.log(`Customer 360 load benchmark against ${BASE_URL}`);
  console.log(`Measurement environment: ${MEASUREMENT_ENVIRONMENT}`);
  console.log(`Warm-up run, then ${RUN_COUNT} measured runs...`);

  const browser = await chromium.launch();
  try {
    const warmupMs = await loadCustomer360Once(browser);
    console.log(`Warm-up: ${warmupMs} ms (discarded)`);

    const samples = [];
    for (let i = 1; i <= RUN_COUNT; i++) {
      const ms = await loadCustomer360Once(browser);
      samples.push(ms);
      console.log(`Run ${i}/${RUN_COUNT}: ${ms} ms`);
    }

    const sorted = [...samples].sort((a, b) => a - b);
    const p50 = percentile(sorted, 50);
    const p95 = percentile(sorted, 95);
    const max = sorted[sorted.length - 1];
    const min = sorted[0];
    const mean = Math.round(samples.reduce((a, b) => a + b, 0) / samples.length);

    const hardware = {
      platform: `${platform()} ${release()}`,
      cpuModel: cpus()[0]?.model ?? "unknown",
      cpuCount: cpus().length,
      totalMemoryGiB: Math.round((totalmem() / 1024 ** 3) * 10) / 10,
      nodeVersion: process.version,
    };

    const numericalTargetPassed = p95 < 2000;
    console.log("\n--- Results ---");
    console.log(`min=${min}ms p50=${p50}ms mean=${mean}ms p95=${p95}ms max=${max}ms`);
    console.log(
      `Numerical target: p95 < 2000ms -- ${numericalTargetPassed ? "PASS" : "FAIL"}`,
    );
    console.log(
      "BRD 10.6 Docker Compose environment requirement: NOT VERIFIED by this run " +
        `(measurement environment: ${MEASUREMENT_ENVIRONMENT})`,
    );

    mkdirSync(REPORT_DIR, { recursive: true });
    const reportPath = join(REPORT_DIR, "e4-s2-customer360-perf-benchmark.md");
    const generatedAt = new Date().toISOString();
    const report = `# E4-S2 AC5: Customer 360 load performance benchmark

Generated: ${generatedAt}

## Status summary

| | |
|---|---|
| Numerical target (p95 < 2,000 ms) | **${numericalTargetPassed ? "PASS" : "FAIL"}** (p95 = ${p95} ms) |
| BRD 10.6 Docker Compose environment requirement | **NOT VERIFIED** |
| Overall E4-S2 AC5 | **${numericalTargetPassed ? "NOT FULLY VERIFIED" : "NOT MET by this measurement"}** |

BRD 10.6 (\`specs/brd/brd.md\`) requires this measurement to be "Measured
locally on Docker Compose". Docker was unavailable in the environment that
produced this run, so it was measured against the repository's documented
non-Docker Windows stack (README.md, "Running without Docker") instead. This
is a **NON-DOCKER OBSERVATIONAL MEASUREMENT**: it provides real evidence
about Customer 360 load performance on this hardware and data volume, but it
does **not** satisfy BRD 10.6's stated environment, and the numerical result
above must not be read as full BRD conformance. The same deviation was
already accepted, and disclosed the same way, for
\`e3-s3-portfolio-perf-benchmark.md\`.

## Method

30 scripted Playwright loads of \`/customers/{accountId}\` (via the persona
switcher, COLLECTIONS_OFFICER, then the Portfolio table's first row) after
one discarded warm-up run, against a database seeded with
\`python -m collectai.bootstrap.cli seed --account-count ${ACCOUNT_COUNT}\`.
"Interactive" is measured as navigation start to the Customer 360
DeterministicPanel's "Rules engine" heading becoming visible -- the panel
that renders Customer 360's core deterministic content (DPD, bucket,
overdue amount, priority band and factors; AC1), and only once
\`GET /api/customers/{account_id}/360\` has returned and been parsed (it sits
inside \`Customer360Screen\`'s \`status === "loaded"\` branch), so it cannot
fire before the primary data has finished loading. Single browser instance,
sequential runs (not parallelized, to avoid resource contention skewing the
measurement).

## Environment

- Measurement environment: **${MEASUREMENT_ENVIRONMENT}** (BRD 10.6 Docker Compose requirement: not verified by this run)
- \`LLM_MODE\`: ${LLM_MODE}
- Seeded accounts: ${ACCOUNT_COUNT}
- Warm-up runs (discarded): 1
- Measured runs: ${RUN_COUNT}

## Hardware

- Platform: ${hardware.platform}
- CPU: ${hardware.cpuModel} (${hardware.cpuCount} logical cores)
- Memory: ${hardware.totalMemoryGiB} GiB total
- Node.js: ${hardware.nodeVersion}

**Caveat:** this run was captured inside a sandboxed development
environment sharing CPU/memory with other processes (the backend API,
PostgreSQL, and the Vite dev server all on the same host), not dedicated
benchmark hardware, and not Docker Compose. Absolute numbers should be
treated as directional; see the status summary above.

## Results (ms)
${samples.map((ms, i) => `- Run ${i + 1}: ${ms}`).join("\n")}

## Summary
| Stat | Value (ms) |
|---|---|
| min | ${min} |
| p50 | ${p50} |
| mean | ${mean} |
| p95 | ${p95} |
| max | ${max} |

**Numerical target: p95 < 2000 ms -- ${numericalTargetPassed ? "PASS" : "FAIL"}**
**BRD 10.6 Docker Compose environment requirement: NOT VERIFIED**
**Overall E4-S2 AC5: ${numericalTargetPassed ? "NOT FULLY VERIFIED (numerical target met; Docker Compose environment not verified)" : "NOT MET by this measurement"}**
`;
    writeFileSync(reportPath, report, "utf-8");
    console.log(`\nReport written to ${reportPath}`);

    // Mirrors the numerical target only (portfolio-load-benchmark.mjs's own convention); it is
    // not, and must not be read as, a BRD 10.6 environment-conformance result -- see the report.
    process.exitCode = numericalTargetPassed ? 0 : 1;
  } finally {
    await browser.close();
  }
}

main().catch((err) => {
  console.error(err);
  process.exitCode = 1;
});
