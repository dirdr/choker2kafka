# Incident workbench

Open the application's base URL after redeploying. `/` serves the workbench; `/incidents/{id}` opens a selected incident. `/health` remains the JSON liveness endpoint, and `/docs` remains the API reference.

FastAPI serves the Jinja template, pinned Tabler 1.7.0 CSS, Tabler 3.49.0 icons and native JavaScript modules from the same container. No separate frontend host, CDN or production Node build is required. Licenses ship with the vendored assets. The interface uses dark surfaces, compact tables and semantic status colors.

The workbench shows transport freshness, a ten-second average event rate, timestamp violation ratio, recent incidents, investigation attempts, recorded tool activity, findings, contracts and recent events. The incident count covers the latest 20 records. Charts contain samples collected since opening the tab; they do not claim to show database history. Raw business timestamps remain integers rather than being interpreted as dates. Browser-unsafe integers are labelled explicitly.

Polling runs every five seconds, pauses when the tab is hidden, and waits for each cycle to finish. You can pause it manually. Partial failures retain previous values with a visible warning. Raw tool bodies and frozen snapshots load only when requested. Every attempt shows its actual model; the header shows the model configured for new attempts.

Use **Producer controls** to change the timestamp unit with a reason. The panel reads and retains the expected revision before submission. A concurrent change returns a conflict and requires reopening the panel. **Retry investigation** appears for the latest failed attempt on an open incident and appends a paid attempt. Reads never trigger retries.

The first write asks for `OPERATOR_TOKEN`. It stays in JavaScript memory for this tab, is sent only in write request headers and clears on reload. It is never embedded in the page or saved in browser storage. The API still enforces authentication and revision checks. Producer controls are manual operator actions; approval-controlled agent repair and automatic resolution remain pending.

## Deployed check

1. Redeploy the latest commit, then open the base URL.
2. Check that the model, transport and detector values load. Open an incident from the left list.
3. Inspect its timeline and finding or failure. Expand one tool result and the frozen evidence.
4. Open **Live stream** and **Contracts**. Check the recorded revision and expected unit.
5. To retry the existing failed incident, click **Retry investigation**, enter the operator token and follow the new attempt. No new fault is required.
6. If the producer still emits seconds, restore milliseconds through **Producer controls** and give the detector about 20 seconds to observe fresh records. The incident stays open until the recovery slice is implemented.

## Browser checks

A Playwright harness covers desktop/mobile layouts, compact reads, on-demand evidence, token handling, configuration writes and escaped model output. Fixture mode intercepts every API request; it never writes to the deployed service. Start the app locally, then run:

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

Local verification passed 91 unit/API tests and a DOM interaction check covering metrics, incident rendering, navigation, on-demand evidence, authenticated writes, token storage and model-output escaping. Nineteen PostgreSQL integration cases remain separately validated through the embedded database adapter. Chromium launch was blocked by the sandbox's macOS process-service restriction; desktop/mobile Playwright execution and screenshots remain to be verified outside that restriction.
