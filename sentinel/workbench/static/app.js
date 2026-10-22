import { api } from "./api.js";
import { wireInvestigatorSettings } from "./settings.js";
import {
  escapeHTML as esc,
  formatTime,
  duration,
  statusClass,
  label,
} from "./format.js";

const byId = (id) => document.getElementById(id);
const state = {
  view: document.body.dataset.incidentId
    ? "detail"
    : { "/stream": "stream", "/contracts": "contracts" }[location.pathname] ||
      "incidents",
  incidents: [],
  contracts: [],
  selected: document.body.dataset.incidentId || null,
  incident: null,
  runs: [],
  run: null,
  chosenRun: null,
  events: [],
  paused: false,
  errors: [],
  detailController: null,
};
let pollTimer;
let notificationTimer;
let detailSequence = 0;
let polling = false;
const badge = (value) =>
  `<span class="badge-state ${statusClass(value)}">${esc(label(value))}</span>`;
const empty = (title, message) =>
  `<div class="empty-state"><h3>${esc(title)}</h3><p>${esc(message)}</p></div>`;

function notify(message, error = false) {
  const element = byId("notification");
  element.textContent = message;
  element.hidden = false;
  element.classList.toggle("bad", error);
  clearTimeout(notificationTimer);
  notificationTimer = setTimeout(
    () => {
      element.hidden = true;
    },
    error ? 12000 : 6500,
  );
}

function setText(id, value, className) {
  const element = byId(id);
  element.textContent = value;
  if (className !== undefined) element.className = className;
}

function renderIncidentList() {
  const filter = byId("incident-filter").value;
  const rows = state.incidents.filter(
    (row) => filter === "all" || row.status === filter,
  );
  const open = state.incidents.filter((row) => row.status === "open").length;
  setText("nav-incident-count", open);
  setText("incident-list-meta", `${rows.length} shown · latest 20 records`);
  byId("incident-list").innerHTML = rows.length
    ? `<div class="table-responsive"><table class="table incident-summary-table"><thead><tr><th>Incident</th><th>Stream / revision</th><th>Status</th><th>Finding</th><th>Detected · UTC</th></tr></thead><tbody>${rows.map((row) => {
        const summary = row.summary || (row.investigation_status === "failed"
          ? "Investigation failed" : ["queued", "running"].includes(row.investigation_status)
            ? "Investigating…" : "Awaiting investigation");
        return `<tr><td><a class="incident-link" href="/incidents/${esc(row.incident_id)}" data-incident="${esc(row.incident_id)}">${esc(row.rule_id)}</a></td><td><span>${esc(row.topic)} / ${esc(row.producer_id)}</span>${row.configuration_revision ? `<span class="row-revision mono">r${esc(row.configuration_revision)}</span>` : ""}</td><td>${badge(row.status)}</td><td class="incident-summary"><p>${esc(summary)}</p></td><td class="mono incident-date">${esc(formatTime(row.opened_at))}</td></tr>`;
      }).join("")}</tbody></table></div>`
    : empty("No incidents", filter === "all" ? "Contract violations will appear here." : `No ${filter} incidents.`);
}

function activityMarkup(incident, run) {
  const rows = [{ at: incident.opened_at, name: "Violation captured", status: "Recorded", result: '<button class="text-button" data-action="snapshot">Evidence</button>' }];
  if (run) {
    rows.push({ at: run.created_at, name: "Investigation queued", status: "Recorded", result: "—" });
    const calls = new Map();
    for (const activity of run.activity || []) {
      const key = activity.tool_call_id || activity.activity_id;
      const call = calls.get(key) || { name: activity.tool_name, at: activity.recorded_at };
      if (activity.phase === "returned") call.returned = activity;
      calls.set(key, call);
    }
    for (const call of calls.values()) {
      const result = call.returned;
      rows.push({
        at: call.at, name: call.name,
        status: result ? "Returned" : run.status === "failed" ? "Interrupted" : "Running",
        result: result ? `<button class="text-button" data-action="tool" data-activity="${esc(result.activity_id)}">${result.document_count == null ? esc(label(result.result_status || "Inspect result")) : `${esc(result.document_count)} documents`}</button>` : "—",
      });
    }
    if (["completed", "failed"].includes(run.status)) rows.push({ at: run.finished_at, name: run.status === "failed" ? "Investigation failed" : "Finding recorded", status: label(run.status), result: "—" });
  }
  return `<div class="table-responsive"><table class="table activity-table"><thead><tr><th>Time · UTC</th><th>Activity</th><th>Status</th><th>Evidence</th></tr></thead><tbody>${rows.map((row) => `<tr><td class="mono">${esc(formatTime(row.at, true))}</td><td>${esc(row.name)}</td><td>${esc(row.status)}</td><td>${row.result}</td></tr>`).join("")}</tbody></table></div>`;
}

function findingMarkup(finding) {
  return `<section class="finding"><div class="finding-verdict">${badge(finding.conclusion)}<span class="muted">${esc(finding.confidence)} confidence</span></div><div class="finding-primary"><div><h4>Likely cause</h4><p>${esc(finding.likely_cause)}</p></div><div><h4>Recommendation</h4><p>${esc(finding.recommendation)}</p></div></div><details id="finding-evidence" class="disclosure"><summary>Supporting evidence</summary><table class="table facts-table"><tbody><tr><th scope="row">Alternatives</th><td><ul>${(finding.alternatives || []).map((item) => `<li>${esc(item)}</li>`).join("")}</ul></td></tr><tr><th scope="row">Declared consumers</th><td>${(finding.affected_consumers || []).map(esc).join(", ") || "Not established"}</td></tr><tr><th scope="row">Attribution</th><td>${finding.attribution ? `${esc(finding.attribution.producer_id)} · r${esc(finding.attribution.configuration_revision)}` : "Not established"}</td></tr><tr><th scope="row">Confidence</th><td>${esc(finding.confidence_rationale)}</td></tr><tr><th scope="row">References</th><td><div class="references">${(finding.evidence_ids || []).map((id) => `<button class="reference" title="${esc(id)}" data-action="reference" data-reference="${esc(id)}">${esc(id)}</button>`).join("")}</div></td></tr></tbody></table></details></section>`;
}

function runMarkup(run) {
  if (!run) return empty("Awaiting investigation", "The worker queues captured incidents automatically.");
  let result;
  if (run.status === "failed") {
    result = `<div class="error-panel"><h4>Investigation failed · ${esc(label(run.error_code || "Unknown error"))}</h4><p>${esc(run.error_detail?.message || "The model did not return a usable finding.")}</p></div>`;
  } else if (run.finding) result = findingMarkup(run.finding);
  else result = empty(run.status === "queued" ? "Queued" : "Investigating", "Tool results appear below as they arrive.");
  const tokens = (run.usage?.input_tokens || 0) + (run.usage?.output_tokens || 0);
  return `<div class="run-toolbar"><label for="attempt-select">Attempt</label><select id="attempt-select" class="form-select form-select-sm attempt-select" aria-label="Investigation attempt">${state.runs.map((attempt, index) => `<option value="${esc(attempt.investigation_id)}" ${run.investigation_id === attempt.investigation_id ? "selected" : ""}>${index === 0 ? "Latest" : "Earlier"} · ${esc(label(attempt.status))}</option>`).join("")}</select><span class="run-model mono">${esc(run.model_id)}</span>${badge(run.status)}</div>${result}<details id="run-diagnostics" class="disclosure"><summary>Execution details · ${esc(duration(run.duration_ms))}</summary><table class="table facts-table"><tbody><tr><th scope="row">Model / agent</th><td>${esc(run.model_id)} / ${esc(run.agent_version)}</td></tr><tr><th scope="row">Tokens reported / allowance</th><td class="mono">${esc(tokens.toLocaleString())} / ${esc(run.token_limit.toLocaleString())}</td></tr><tr><th scope="row">Deadline</th><td>${esc(run.deadline_seconds ?? 45)}s</td></tr><tr><th scope="row">Requests / tool calls</th><td>${esc(run.usage?.requests ?? 0)} / ${esc(run.usage?.tool_calls ?? 0)}</td></tr><tr><th scope="row">Run ID</th><td class="mono">${esc(run.investigation_id)}</td></tr>${run.error_detail?.fields ? `<tr><th scope="row">Validation errors</th><td>${run.error_detail.fields.map((field) => `${esc(field.path)}: ${esc(label(field.type))}`).join("<br>")}</td></tr>` : ""}</tbody></table></details>`;
}

function renderDetail() {
  const incident = state.incident;
  if (!incident || document.activeElement?.id === "attempt-select") return;
  const expanded = [...byId("incident-detail").querySelectorAll("details[open]")].map((element) => element.id);
  byId("incident-detail").innerHTML = `<div class="detail-heading"><h2>${esc(incident.rule_id)}</h2>${badge(incident.status)}</div><div class="table-responsive"><table class="table incident-context"><thead><tr><th>Stream</th><th>Producer revision</th><th>Contract</th><th>Fields</th></tr></thead><tbody><tr><td>${esc(incident.topic)}</td><td>${esc(incident.producer_id)}${incident.configuration_revision ? ` · r${esc(incident.configuration_revision)}` : ""}</td><td>${esc(incident.contract_id)} v${esc(incident.contract_version)}</td><td>${esc(incident.affected_fields.join(", "))}</td></tr></tbody></table></div><section class="investigation-section"><div class="section-heading"><h3>Investigation</h3><button class="text-button" data-action="signal">Captured signal</button></div>${runMarkup(state.run)}</section><section class="activity-section"><div class="section-heading"><h3>Activity</h3><small>Recorded tool calls · UTC</small></div>${activityMarkup(incident, state.run)}</section>`;
  for (const id of expanded) { const element = byId(id); if (element) element.open = true; }
  byId("attempt-select")?.addEventListener("change", (event) => {
    state.chosenRun = event.target.value;
    refreshDetail();
  });
}

async function refreshDetail() {
  if (!state.selected) return;
  state.detailController?.abort();
  const controller = new AbortController();
  state.detailController = controller;
  const sequence = ++detailSequence;
  try {
    const [incident, runs] = await Promise.all([
      api(`/api/incidents/${state.selected}`, { signal: controller.signal }),
      api(`/api/incidents/${state.selected}/investigations`, {
        signal: controller.signal,
      }),
    ]);
    const chosen =
      runs.find((run) => run.investigation_id === state.chosenRun) || runs[0];
    const run = chosen
      ? await api(`/api/investigations/${chosen.investigation_id}`, {
          signal: controller.signal,
        })
      : null;
    if (sequence !== detailSequence) return;
    state.incident = incident;
    state.runs = runs;
    state.run = run;
    renderDetail();
  } catch (error) {
    if (error.name === "AbortError" || sequence !== detailSequence) return;
    byId("incident-detail").innerHTML = empty(
      "Incident unavailable",
      error.message,
    );
  }
}

function selectIncident(id, updateHistory = true) {
  if (state.selected === id && state.incident) return;
  state.selected = id;
  state.incident = null;
  state.run = null;
  state.runs = [];
  state.chosenRun = null;
  if (updateHistory)
    history.pushState({}, "", `/incidents/${encodeURIComponent(id)}`);
  renderIncidentList();
  showView("detail");
  byId("incident-detail").innerHTML = empty(
    "Loading incident",
    "Reading the recorded signal and investigation attempts.",
  );
  refreshDetail();
}

function renderContracts() {
  byId("contracts-body").innerHTML = state.contracts.length
    ? `<div class="table-responsive"><table class="table contracts-table"><thead><tr><th>Contract</th><th>Topic</th><th>Version</th><th>Rules</th></tr></thead><tbody>${state.contracts.map((contract) => `<tr><td>${esc(contract.contract_id)}</td><td>${esc(contract.topic)}</td><td class="mono">${esc(contract.version)}</td><td><details class="disclosure"><summary>${contract.rules.length} ${contract.rules.length === 1 ? "rule" : "rules"}</summary>${contract.rules.map((rule) => `<div class="contract-definition"><strong>${esc(rule.rule_id)}</strong><dl><dt>Type</dt><dd>${esc(rule.kind)}</dd><dt>Fields</dt><dd>${esc(rule.fields.join(", "))}</dd>${Object.entries(rule.parameters).map(([key, value]) => `<dt>${esc(label(key))}</dt><dd>${esc(typeof value === "object" ? JSON.stringify(value) : value)}</dd>`).join("")}</dl></div>`).join("")}</details></td></tr>`).join("")}</tbody></table></div>`
    : empty("No contracts", "No contract versions recorded for this topic.");
}

async function refreshEvents() {
  try {
    const events = await api("/api/events?limit=20");
    state.events = events;
    byId("events-body").innerHTML = events.length
      ? events
          .map(
            (event) =>
              `<tr><td class="mono">${esc(formatTime(event.ingested_at))}</td><td>${esc(event.topic || "—")}</td><td>${esc(event.producer_id || "—")} <span class="muted mono">r${esc(event.config_revision)}</span></td><td class="mono">${esc(event.partition)} / ${esc(event.kafka_offset)}</td><td><button class="text-button" data-event="${esc(event.event_id)}">Inspect</button></td></tr>`,
          )
          .join("")
      : '<tr><td colspan="5">No accepted events recorded.</td></tr>';
  } catch (error) {
    byId("events-body").innerHTML =
      `<tr><td colspan="5">${esc(error.message)}</td></tr>`;
  }
}

async function refreshOverview() {
  const endpoints = [
    "/api/stream",
    "/api/detection",
    "/api/investigation",
    "/api/incidents?limit=20",
  ];
  const names = [
    "Stream",
    "Detection",
    "Investigation",
    "Incidents",
  ];
  const results = await Promise.allSettled(
    endpoints.map((endpoint) => api(endpoint)),
  );
  const values = results.map((result) =>
    result.status === "fulfilled" ? result.value : null,
  );
  state.errors = results.flatMap((result, index) =>
    result.status === "rejected"
      ? [`${names[index]}: ${result.reason.message}`]
      : [],
  );
  const [stream, detection, investigator, incidents] = values;
  if (stream) {
    setText("metric-throughput", (stream.recent_events / 10).toFixed(1), "mono");
    setText("metric-rejected", stream.recent_rejections ?? "—", "mono");
    setText(
      "metric-transport",
      label(stream.transport),
      statusClass(stream.transport),
    );
    setText(
      "metric-transport-detail",
      `Last record ${formatTime(stream.last_ingested_at, true)}`,
    );
  }
  if (detection) {
    setText("sidebar-topic", detection.topic);
  }
  if (investigator) {
    setText(
      "configured-model",
      investigator.model_id || "Model metadata unavailable",
    );
    setText(
      "agent-version",
      `${(investigator.token_limit || 0).toLocaleString()} tokens per attempt`,
    );
  }
  if (incidents) {
    state.incidents = incidents;
    renderIncidentList();
  }
  const errors = byId("source-errors");
  errors.hidden = state.errors.length === 0;
  errors.textContent = `${state.errors.join(" · ")}${state.errors.length ? ". Last successful values remain visible." : ""}`;
  const ok = state.errors.length === 0;
  setText(
    "last-updated",
    `Updated ${formatTime(Date.now(), true)} UTC${ok ? "" : " · partial update"}`,
  );
}

async function tick() {
  if (state.paused || document.hidden || polling) return;
  polling = true;
  try {
    await refreshOverview();
    await Promise.allSettled([
      state.view === "detail" && state.selected && refreshDetail(),
      state.view === "stream" && refreshEvents(),
    ]);
  } catch (error) {
    notify(error.message, true);
  } finally {
    polling = false;
    clearTimeout(pollTimer);
    if (!state.paused && !document.hidden) pollTimer = setTimeout(tick, 5000);
  }
}

function showView(view) {
  state.view = view;
  for (const element of document.querySelectorAll("[data-view]")) {
    const active =
      element.dataset.view === view ||
      (view === "detail" && element.dataset.view === "incidents");
    element.classList.toggle("active", active);
    if (active) element.setAttribute("aria-current", "page");
    else element.removeAttribute("aria-current");
  }
  for (const name of ["incidents", "detail", "stream", "contracts"])
    byId(`view-${name}`).hidden = name !== view;
  setText(
    "view-title",
    {
      incidents: "Incidents",
      detail: "Incident",
      stream: "Live stream",
      contracts: "Contracts",
    }[view],
  );
  const titles = {
    incidents: "Incidents",
    detail: "Incident details",
    stream: "Live stream",
    contracts: "Contracts",
  };
  setText("page-title", titles[view]);
  document.title = `Sentinel · ${titles[view]}`;
  setText(
    "page-description",
    {
      incidents: "Contract violations and investigation results.",
      detail: "Captured evidence and recorded agent activity.",
      stream: "Ingestion and recent records.",
      contracts: "Versioned expectations for the stream.",
    }[view],
  );
  if (view === "incidents") {
    state.detailController?.abort();
    state.selected = null;
    state.incident = null;
    state.run = null;
  }
  const path =
    view === "detail"
      ? `/incidents/${state.selected}`
      : { incidents: "/", stream: "/stream", contracts: "/contracts" }[view];
  if (path && location.pathname !== path) history.pushState({}, "", path);
  if (view === "stream") {
    refreshEvents();
  }
  if (view === "contracts") loadContracts();
}

async function loadContracts() {
  try {
    state.contracts = await api("/api/contracts?limit=20");
    renderContracts();
  } catch (error) {
    byId("contracts-body").innerHTML = empty(
      "Contracts unavailable",
      error.message,
    );
  }
}

function showEvidence(title, value, subtitle = "Captured source data") {
  setText("evidence-title", title);
  setText("evidence-subtitle", subtitle);
  setText(
    "evidence-body",
    typeof value === "string" ? value : JSON.stringify(value, null, 2),
  );
  const dialog = byId("evidence-dialog");
  if (!dialog.open) dialog.showModal();
}

async function inspectEvidence(action, target) {
  const incident = state.incident;
  const run = state.run;
  if (!incident) return;
  try {
    if (action === "signal")
      return showEvidence(
        "Captured signal",
        incident.signal,
        `Incident ${incident.incident_id}`,
      );
    if (action === "snapshot") {
      const snapshot = await api(
        `/api/incidents/${incident.incident_id}/evidence`,
      );
      return showEvidence(
        "Frozen incident evidence",
        snapshot,
        `Captured ${formatTime(snapshot.captured_at)}`,
      );
    }
    if (!run) return;
    const detail = await api(
      `/api/investigations/${run.investigation_id}?include_activity_bodies=true`,
    );
    if (action === "tool") {
      const activity = detail.activity.find(
        (item) => item.activity_id === target.dataset.activity,
      );
      if (activity)
        showEvidence(
          activity.tool_name,
          activity.body,
          `${label(activity.phase)} · ${formatTime(activity.recorded_at)}`,
        );
    } else {
      const reference = target.dataset.reference;
      const documents = detail.activity.flatMap(
        (item) => item.body?.documents || [],
      );
      const document = documents.find((item) => item.evidence_id === reference);
      showEvidence(
        reference,
        document?.data || {
          detail: "Reference not present in archived tool documents",
        },
        "Evidence returned to this investigation",
      );
    }
  } catch (error) {
    notify(error.message, true);
  }
}

document.addEventListener("click", (event) => {
  const nav = event.target.closest("[data-view]");
  if (nav) showView(nav.dataset.view);
  const row = event.target.closest("[data-incident]");
  if (row) {
    event.preventDefault();
    selectIncident(row.dataset.incident);
  }
  const closer = event.target.closest("[data-close]");
  if (closer) byId(closer.dataset.close).close();
  const record = event.target.closest("[data-event]");
  if (record) {
    const entry = state.events.find((item) => item.event_id === record.dataset.event);
    if (entry) showEvidence("Event record", entry, "Stored stream record");
  }
  const action = event.target.closest("[data-action]");
  if (action) inspectEvidence(action.dataset.action, action);
});
byId("incident-filter").addEventListener("change", renderIncidentList);
byId("pause-button").addEventListener("click", () => {
  state.paused = !state.paused;
  clearTimeout(pollTimer);
  setText("pause-button", state.paused ? "Resume" : "Pause");
  byId("pause-button").setAttribute("aria-pressed", String(state.paused));
  if (!state.paused) tick();
});
document.addEventListener("visibilitychange", () => {
  clearTimeout(pollTimer);
  if (!document.hidden && !state.paused) tick();
});
window.addEventListener("popstate", () => {
  const match = location.pathname.match(/^\/incidents\/([a-f0-9-]+)$/i);
  state.selected = null;
  state.incident = null;
  if (match) selectIncident(match[1], false);
  else
    showView(
      { "/stream": "stream", "/contracts": "contracts" }[location.pathname] ||
        "incidents",
    );
});
window.addEventListener("pagehide", () => {
  clearTimeout(pollTimer);
  state.detailController?.abort();
});
byId("back-to-incidents").addEventListener("click", () =>
  showView("incidents"),
);
showView(state.view);
loadContracts();
tick();

wireInvestigatorSettings(async () => {
  notify("Investigator settings saved");
  await refreshOverview();
});
