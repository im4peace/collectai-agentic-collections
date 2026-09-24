// E3-S3 AC5 performance benchmark: "Portfolio main content is interactive
// in under 2 s p95 over 30 scripted Playwright loads after one warm-up on
// the 1,000-account dataset." specs/design/deployment.md: a **manually
// triggered** script (not part of `make test`/CI, since CI runners are not
// representative hardware), 30 runs after one warm-up, hardware recorded,
// result committed to `docs/portfolio/`.
//
// Usage (from `frontend/`, with the backend API and `npm run dev` already
// running against a database seeded with `--account-count 1000`):
//   node e2e/perf/portfolio-load-benchmark.mjs [baseURL]
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
const BASE_URL = process.argv[2] ?? "http://localhost:5173";
const __dirname = dirname(fileURLToPath(import.meta.url));
const REPORT_DIR = join(__dirname, "..", "..", "..", "docs", "portfolio");

async function loadPortfolioOnce(browser) {
  const page = await browser.newPage();
  const start = Date.now();
  await page.goto(BASE_URL + "/");
  await page.getByRole("radio", { name: /COLLECTIONS_OFFICER/ }).click();
  await page.getByRole("button", { name: "Use this persona" }).click();
  await page.getByRole("table").waitFor({ state: "visible" });
  const elapsedMs = Date.now() - start;
  await page.close();
  return elapsedMs;
}

function percentile(sorted, p) {
  const index = Math.min(sorted.length - 1, Math.ceil((p / 100) * sorted.length) - 1);
  return sorted[Math.max(0, index)];
}

async function main() {
  console.log(`Portfolio load benchmark against ${BASE_URL}`);
  console.log(`Warm-up run, then ${RUN_COUNT} measured runs...`);

  const browser = await chromium.launch();
  try {
    const warmupMs = await loadPortfolioOnce(browser);
    console.log(`Warm-up: ${warmupMs} ms (discarded)`);

    const samples = [];
    for (let i = 1; i <= RUN_COUNT; i++) {
      const ms = await loadPortfolioOnce(browser);
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
    };

    const passed = p95 < 2000;
    console.log("\n--- Results ---");
    console.log(`min=${min}ms p50=${p50}ms mean=${mean}ms p95=${p95}ms max=${max}ms`);
    console.log(`AC5 target: p95 < 2000ms -- ${passed ? "PASS" : "FAIL"}`);

    mkdirSync(REPORT_DIR, { recursive: true });
    const reportPath = join(REPORT_DIR, "e3-s3-portfolio-perf-benchmark.md");
    const generatedAt = new Date().toISOString();
    const report = `# E3-S3 AC5: Portfolio load performance benchmark

Generated: ${generatedAt}

## Method
30 scripted Playwright loads of \`/portfolio\` (via the persona switcher,
COLLECTIONS_OFFICER) after one discarded warm-up run, against a database
seeded with \`python -m collectai.bootstrap.cli seed --account-count 1000\`.
"Interactive" is measured as navigation start to the Portfolio table
becoming visible. Single browser instance, sequential runs (not
parallelized, to avoid resource contention skewing the measurement).

## Hardware
- Platform: ${hardware.platform}
- CPU: ${hardware.cpuModel} (${hardware.cpuCount} logical cores)
- Memory: ${hardware.totalMemoryGiB} GiB total

**Caveat:** this run was captured inside a sandboxed development
environment sharing CPU/memory with other processes (the backend API,
PostgreSQL, and the Vite dev server all on the same host), not dedicated
benchmark hardware. Absolute numbers should be treated as directional; see
the note in the report's summary.

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

**AC5 target: p95 < 2000 ms -- ${passed ? "PASS" : "FAIL"}**
`;
    writeFileSync(reportPath, report, "utf-8");
    console.log(`\nReport written to ${reportPath}`);

    process.exitCode = passed ? 0 : 1;
  } finally {
    await browser.close();
  }
}

main().catch((err) => {
  console.error(err);
  process.exitCode = 1;
});
