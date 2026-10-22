import assert from "node:assert/strict";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { chromium } from "playwright";
import { escapeHTML as esc } from "../../sentinel/workbench/static/format.js";
import { collectEvidence } from "./evidence-data.mjs";

const base = (process.env.SENTINEL_BASE_URL || "http://127.0.0.1:8080").replace(/\/$/, "");
const incidentId = process.env.SENTINEL_INCIDENT_ID;
assert.ok(incidentId, "Set SENTINEL_INCIDENT_ID to the resolved demo incident UUID");
const output = path.resolve(process.env.SENTINEL_EVIDENCE_DIR || "test-results/evidence");
const read = async (endpoint) => {
  const response = await fetch(base + endpoint, { signal: AbortSignal.timeout(15000) });
  assert.ok(response.ok, `Read failed (${response.status}): ${endpoint}`);
  return response.json();
};
const bundle = await collectEvidence(read, incidentId);
await mkdir(output, { recursive: true });
await writeFile(path.join(output, "evidence.json"), JSON.stringify(bundle, null, 2));
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
  const application = new URL(base).origin;
  await page.route(`${application}/**`, (route) => {
    assert.equal(route.request().method(), "GET", "Evidence export must not change the application");
    return route.continue();
  });
  await page.goto(`${base}/incidents/${incidentId}`, { waitUntil: "domcontentloaded" });
  await page.locator("#attempt-select").waitFor();
  if (await page.locator("#attempt-select").inputValue() !== bundle.run.investigation_id)
    await page.locator("#attempt-select").selectOption(bundle.run.investigation_id);
  await page.waitForFunction((model) => document.querySelector("#incident-detail .run-model")?.textContent === model, bundle.run.model_id);
  await page.locator(".repair-section").waitFor();
  await page.evaluate(() => document.fonts.ready);
  await page.locator("#pause-button").click();
  const capture = async (name, locator) => {
    const target = path.join(output, `${name}.png`);
    await locator.screenshot({ path: target });
    return `data:image/png;base64,${(await readFile(target)).toString("base64")}`;
  };
  const finding = await capture("finding", page.locator(".investigation-section"));
  const activity = await capture("tool-activity", page.locator(".activity-section"));
  const recovery = await capture("repair-and-recovery", page.locator(".repair-section"));
  await page.locator('[data-action="signal"]').click();
  const before = await capture("captured-violation", page.locator("#evidence-dialog"));
  const metric = (value, suffix = "") => value == null ? "Not recorded" : `${value.toLocaleString("en-GB", { maximumFractionDigits: 1 })}${suffix}`;
  const m = bundle.metrics;
  const failure = metric(bundle.contract.failure_ratio * 100, "%");
  const html = `<!doctype html><html><head><meta charset="utf-8"><title>Sentinel evidence</title><style>
    @page{size:A4;margin:14mm}*{box-sizing:border-box}body{font:12px/1.5 Arial,sans-serif;color:#222;margin:0}h1{font-size:30px;margin:0 0 5px;letter-spacing:-1px}h2{font-size:18px;margin:20px 0 10px}p{margin:5px 0 12px}.page{break-after:page}.page:last-child{break-after:auto}.muted{color:#666}.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.shot{margin:0;min-width:0}.shot img{width:100%;height:175px;object-fit:contain;object-position:top;background:#111}.shot figcaption{font-size:11px;margin-top:5px}table{border-collapse:collapse;width:100%;margin:10px 0 18px}th,td{text-align:left;vertical-align:top;padding:9px 7px;border-bottom:1px solid #ddd}th{font-weight:600}code{font-size:10px;overflow-wrap:anywhere}a{color:#333}footer{font-size:10px;color:#666;margin-top:18px}.quote{font-size:14px;border-left:2px solid #aaa;padding-left:12px;margin:16px 0}
    </style></head><body><section class="page"><h1>Sentinel</h1><p class="muted">One recorded journey from contract breach to verified recovery</p><p><strong>Before:</strong> revision ${esc(bundle.faulty.revision)} emits ${esc(bundle.faulty.event_time_unit)}. The integer check accepts ${esc(bundle.baseline.accepted)}/${esc(bundle.baseline.samples)} captured samples; the contract evaluation records ${esc(failure)} violations.</p><p><strong>After:</strong> PR #${esc(bundle.repair.pr_number)} is merged, revision ${esc(bundle.repair.recovery_revision)} passes two fresh windows, and the incident is resolved.</p><div class="grid"><figure class="shot"><img src="${before}"><figcaption>Frozen signal from the failing window.</figcaption></figure><figure class="shot"><img src="${finding}"><figcaption>Evidence-linked finding and recommendation.</figcaption></figure><figure class="shot"><img src="${activity}"><figcaption>Recorded tool checks and results.</figcaption></figure><figure class="shot"><img src="${recovery}"><figcaption>Repair PR and verified recovery.</figcaption></figure></div><p class="quote">${esc(bundle.run.finding.likely_cause)}</p><footer>Incident ${esc(incidentId)} · Actual captured evidence; no fixture screenshots.<br>Faulty source commit: ${esc(bundle.faulty.source_commit || "Not recorded")}<br>Repair: <a href="${esc(bundle.repair.pr_url)}">${esc(bundle.repair.pr_url)}</a></footer></section><section class="page"><h1>Measured evidence</h1><p class="muted">A narrow baseline, with each contribution stated separately</p><table><thead><tr><th>Check</th><th>Integer type baseline</th><th>Sentinel</th></tr></thead><tbody><tr><td>Payload timestamp type</td><td>${esc(bundle.baseline.accepted)}/${esc(bundle.baseline.samples)} accepted</td><td>Events accepted by ingestion</td></tr><tr><td>Meaning of the value</td><td>Not evaluated</td><td>${esc(bundle.contract.status)} · ${esc(failure)} captured failures</td></tr><tr><td>Producer attribution</td><td>Not evaluated</td><td>Revision ${esc(bundle.faulty.revision)}, with cited evidence</td></tr><tr><td>Repair and outcome</td><td>Not evaluated</td><td>PR #${esc(bundle.repair.pr_number)} and two verified recovery windows</td></tr></tbody></table><h2>Recorded run</h2><table><tbody><tr><th>Detection</th><td>${esc(metric(m.detection_seconds, "s"))} after faulty configuration became active</td></tr><tr><th>Investigation</th><td>${esc(metric(m.investigation_seconds, "s"))}</td></tr><tr><th>Reported tokens</th><td>${esc(metric(m.reported_tokens))} · ${esc(metric(m.model_requests))} model requests · ${esc(metric(m.tool_calls))} tool calls</td></tr><tr><th>Recovery</th><td>${esc(metric(m.recovery_seconds, "s"))} after repaired configuration became active</td></tr><tr><th>Model</th><td>${esc(bundle.run.model_id)}</td></tr><tr><th>Recovery samples</th><td>${bundle.repair.recovery_windows.map((window) => esc(window.evidence.samples)).join(" + ")} events across separate ten-second windows</td></tr></tbody></table><h2>What this proves</h2><p>The baseline checks timestamp type only. Contract detection is deterministic. The agent adds the diagnosis and evidence references; a constrained adapter opens the PR. Fresh passing data establishes recovery.</p><p>This is one synthetic demo run, not a production benchmark or an average latency claim. Reported usage may omit tokens from interrupted provider requests.</p><h2>Data layer</h2><p>Aiven Kafka carries events. Aiven PostgreSQL stores contracts, revisions, frozen evidence, investigations and recovery records. The agent reads the captured snapshot through typed tools.</p><footer>Exported ${esc(bundle.exported_at)}<br>Run ${esc(bundle.run.investigation_id)} · Full measurements are included in evidence.json.</footer></section></body></html>`;
  await writeFile(path.join(output, "report.html"), html);
  await page.unrouteAll();
  await page.setContent(html, { waitUntil: "load" });
  await page.pdf({ path: path.join(output, "sentinel-evidence.pdf"), format: "A4", printBackground: true, preferCSSPageSize: true });
  console.log(`Evidence PDF, measurements and screenshots saved to ${output}`);
} finally {
  await browser.close();
}
