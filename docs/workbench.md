# Incident workbench

Open the application's base URL after redeploying. `/` lists incident summaries without selecting one. `/incidents/{id}` opens its details; `/stream` holds stream metrics and records, and `/contracts` lists contract versions. `/health` remains the JSON liveness endpoint, and `/docs` remains the API reference.

FastAPI serves the Jinja template, pinned Tabler 1.7.0 CSS, Tabler 3.49.0 icons and native JavaScript modules from the same container. No separate frontend host, CDN or production Node build is required. Licenses ship with the vendored assets. The interface uses dark surfaces, compact tables and semantic status colors.

The workbench shows transport freshness, a ten-second average event rate, timestamp violation ratio, recent incidents, investigation attempts, recorded tool activity, findings, contracts and recent events. The incident count covers the latest 20 records. Charts contain samples collected since opening the tab; they do not claim to show database history. Raw business timestamps remain integers rather than being interpreted as dates. Browser-unsafe integers are labelled explicitly.

Polling runs every five seconds, pauses when the tab is hidden, and waits for each cycle to finish. You can pause it manually. Partial failures retain previous values with a visible warning. Raw tool bodies and frozen snapshots load only when requested. Every attempt shows its actual model; the header shows the model configured for new attempts.

The workbench is read-only. Producer changes and investigation retries stay in Bruno/API. It never requests an operator token and makes only GET requests. External operator APIs still require their bearer token. Configuration history remains available as evidence.

## Deployed check

1. Redeploy the latest commit, then open the base URL.
2. Check that the model, transport and detector values load. Open an incident from the left list.
3. Inspect its timeline and finding or failure. Expand one tool result and the frozen evidence.
4. Open **Live stream** and **Contracts**. Check the recorded revision and expected unit.
5. To retry an existing failed attempt, use **Retry failed investigation** in Bruno, then keep its workbench detail open to watch the new run. No new fault is required for that retry.
6. A new faulty configuration revision opens a separate incident automatically. Repeated bad windows from that revision reuse its incident. Restore milliseconds in Bruno when finished; closure still requires the pending recovery implementation.

## Browser checks

A Playwright harness covers desktop/mobile layouts, compact reads, on-demand evidence, incident-list navigation, read-only requests and escaped model output. Fixture mode intercepts every API request and asserts that each request is a GET. Start the app locally, then run:

```sh
npm --prefix tools/browser ci
npm --prefix tools/browser exec -- playwright install chromium
npm --prefix tools/browser test
```

To check a deployed workbench with read-only browser actions:

```sh
SENTINEL_BASE_URL=https://YOUR-RUNTIME-URL npm --prefix tools/browser run test:live
```

Screenshots go to `tools/browser/test-results`. Fixture screenshots represent test data. Live mode reads the real deployment and makes no configuration changes or investigation retries.

Local verification passed 91 unit/API tests and a DOM interaction check covering summary-first navigation, separate detail/stream/contract views, on-demand evidence, read-only requests and model-output escaping. Nineteen PostgreSQL integration cases remain separately validated through the embedded database adapter. Chromium launch was blocked by the sandbox's macOS process-service restriction; desktop/mobile Playwright execution and screenshots remain to be verified outside that restriction.
