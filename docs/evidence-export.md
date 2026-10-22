# Export the submission evidence

Complete one real incident first: commit the faulty configuration, obtain a supported finding and a repair PR, merge it, and wait for verified recovery. The exporter refuses open incidents and unverified repairs.

Install the pinned browser tools and Chromium in an environment that permits browser launch:

```sh
npm --prefix tools/browser ci
npm --prefix tools/browser exec -- playwright install chromium
```

From the repository root, export the resolved incident:

```sh
SENTINEL_BASE_URL=https://YOUR-RUNTIME-URL \
SENTINEL_INCIDENT_ID=YOUR-RESOLVED-INCIDENT-UUID \
npm --prefix tools/browser run evidence
```

Output is written to `tools/browser/test-results/evidence`: `sentinel-evidence.pdf`, `report.html`, `evidence.json`, and four screenshots. The exporter makes only read requests. It does not introduce a fault, call the model, open a PR or change configuration.

Page one shows the captured violation, finding, tool activity, and repair/recovery. Page two compares a timestamp integer-type check with the recorded contract evaluation and reports measured detection, investigation, token usage and recovery. This is one synthetic end-to-end run; it is not a statistical benchmark or a comparison against an agent without data.

Detection time starts when the faulty revision becomes active in PostgreSQL. Recovery time starts when the repaired revision becomes active. Missing measurements are labelled **Not recorded**. The exporter saves the underlying measurements so every number can be checked.

Inspect the PDF before uploading. Capture the faulty GitHub commit separately if you want a GitHub screenshot in the final layout; its source commit and repair PR link are recorded in the report. No private GitHub browser session is required by the exporter.

The current sandbox blocks Chromium launch through the macOS process service. Data validation tests run here; screenshot and PDF rendering must be verified outside that restriction.

## Recorded report available now

The checked report in `artifacts/evidence/sentinel-evidence.pdf` uses deployed incident `3f879fa2-bea9-45ec-840e-3a3612d55e7c`, PR #1, and repaired revision 8. It contains the measured before/after and baseline comparison in two pages. `evidence.json` retains the API measurements. This report uses vector text and tables; it does not contain browser screenshots.

Regenerate that report in an environment with Matplotlib installed:

```sh
python3 tools/evidence/build_pdf.py artifacts/evidence/evidence.json artifacts/evidence/sentinel-evidence.pdf
```

The Playwright exporter above produces a separate screenshot version when Chromium can launch. Its measurement validation tests cover the recorded time boundaries and reject incomplete or overlapping recovery evidence.
