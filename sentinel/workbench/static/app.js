import { api } from "./api.js";
import {
  escapeHTML as esc,
  formatTime,
  rawInteger,
  percent,
  duration,
  statusClass,
  label,
} from "./format.js";
import { drawChart } from "./charts.js";

const byId = (id) => document.getElementById(id);
const state = {
  view: document.body.dataset.incidentId
    ? "detail"
    : { "/stream": "stream", "/contracts": "contracts" }[location.pathname] ||
      "incidents",
  incidents: [],
  configuration: null,
  contracts: [],
  selected: document.body.dataset.incidentId || null,
  incident: null,
  runs: [],
  run: null,
  chosenRun: null,
  samples: [],
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

function chartRender() {
  drawChart(byId("throughput-chart"), state.samples, "throughput", "#82c69b");
  drawChart(byId("failure-chart"), state.samples, "failure", "#ed9b54", 100);
  if (state.samples.length)
    setText("chart-start", formatTime(state.samples[0].at, true));
  setText("chart-samples", `${state.samples.length} samples in this tab`);
}

function renderConfiguration() {
  const configuration = state.configuration;
  byId("stream-configuration").innerHTML = configuration
    ? `<span>Producer <strong>${esc(configuration.producer_id)}</strong></span><span>Unit <strong class="mono">${esc(configuration.event_time_unit)}</strong></span><span>Revision <strong class="mono">${esc(configuration.revision)}</strong></span>`
    : "Configuration unavailable";
}

function renderIncidentList() {
  const filter = byId("incident-filter").value;
  const rows = state.incidents.filter(
    (row) => filter === "all" || row.status === filter,
  );
  const open = state.incidents.filter((row) => row.status === "open").length;
  setText("metric-incidents", open);
  setText("nav-incident-count", open);
  setText("incident-list-meta", `${rows.length} shown · latest 20 records`);
  byId("incident-list").innerHTML = rows.length
    ? `<div class="table-responsive"><table class="table incident-summary-table"><thead><tr><th>Incident</th><th>Summary</th><th>Investigation</th><th>Detected · UTC</th><th></th></tr></thead><tbody>${rows
        .map((row) => {
          const summary =
            row.summary ||
            (row.investigation_status === "failed"
              ? "Investigation failed. Review its tool activity or retry."
              : ["queued", "running"].includes(row.investigation_status)
                ? "Investigation in progress. Live activity is available."
                : "Contract violation captured. Waiting for investigation.");
          return `<tr><td><a class="incident-link" href="/incidents/${esc(row.incident_id)}" data-incident="${esc(row.incident_id)}">${esc(row.rule_id)}</a><div class="row-meta">${esc(row.topic)} / ${esc(row.producer_id)}${row.configuration_revision ? ` · r${esc(row.configuration_revision)}` : ""} · ${esc(row.affected_fields.join(", "))}</div><div class="row-status">${badge(row.status)}<span class="mono">${esc(row.incident_id.slice(0, 8))}</span></div></td><td class="incident-summary"><p>${esc(summary)}</p><div class="row-meta">${esc(row.contract_id)} · v${esc(row.contract_version)}</div></td><td>${badge(row.investigation_status || "pending")}${row.model_id ? `<div class="row-meta mono">${esc(row.model_id)}</div>` : ""}</td><td class="mono incident-date">${esc(formatTime(row.opened_at))}</td><td><a class="text-button" href="/incidents/${esc(row.incident_id)}" data-incident="${esc(row.incident_id)}">Open</a></td></tr>`;
        })
        .join("")}</tbody></table></div>`
    : empty(
        "No incidents",
        filter === "all"
          ? "Captured contract violations will appear here."
          : `No ${filter} incidents in the latest records.`,
      );
}

function timelineMarkup(incident, run) {
  const entries = [
    {
      kind: "detected",
      at: incident.opened_at,
      title: "Contract violation captured",
      description: `${incident.contract_id} · v${incident.contract_version}`,
      action:
        '<button class="text-button" data-action="snapshot">Inspect frozen evidence</button>',
    },
  ];
  if (run) {
    entries.push({
      kind: "started",
      at: run.created_at,
      title: "Investigation queued",
      description: `${run.model_id} · ${run.agent_version}`,
    });
    for (const activity of run.activity || []) {
      const returned = activity.phase === "returned";
      const count = activity.document_count;
      entries.push({
        kind: activity.phase,
        at: activity.recorded_at,
        title: `${activity.tool_name} ${returned ? "returned" : "started"}`,
        description: returned
          ? count == null
            ? activity.result_status
              ? label(activity.result_status)
              : "Result recorded"
            : `${count} evidence documents`
          : "Reading captured evidence",
        action: returned
          ? `<button class="text-button" data-action="tool" data-activity="${esc(activity.activity_id)}">Inspect result</button>`
          : "",
      });
    }
    if (["completed", "failed"].includes(run.status))
      entries.push({
        kind: run.status === "failed" ? "failed" : "returned",
        at: run.finished_at,
        title:
          run.status === "failed" ? "Investigation failed" : "Finding recorded",
        description:
          run.status === "failed"
            ? run.error_detail?.message || label(run.error_code)
            : "Evidence references validated",
      });
  }
  return entries
    .map(
      (entry) =>
        `<li class="${esc(entry.kind)}"><h4>${esc(entry.title)}</h4><p>${esc(entry.description)}</p>${entry.action || ""}<time>${esc(formatTime(entry.at))}</time></li>`,
    )
    .join("");
}

function findingMarkup(finding) {
  const consumers = finding.affected_consumers || [];
  return `<div class="finding"><h4>Conclusion</h4><div>${badge(finding.conclusion)} <span class="muted">${esc(finding.confidence)} confidence</span></div><h4>Likely cause</h4><p>${esc(finding.likely_cause)}</p><h4>Alternative explanations</h4><ul>${(finding.alternatives || []).map((item) => `<li>${esc(item)}</li>`).join("")}</ul><h4>Declared consumer impact</h4><p>${consumers.length ? consumers.map(esc).join(", ") : "No affected consumers established"}</p>${finding.attribution ? `<h4>Attributed configuration</h4><p class="mono">${esc(finding.attribution.producer_id)} · revision ${esc(finding.attribution.configuration_revision)}</p>` : ""}<h4>Recommendation</h4><p>${esc(finding.recommendation)}</p><h4>Confidence rationale</h4><p>${esc(finding.confidence_rationale)}</p><h4>Evidence references</h4><div class="references">${(finding.evidence_ids || []).map((id) => `<button class="reference" title="${esc(id)}" data-action="reference" data-reference="${esc(id)}">${esc(id)}</button>`).join("")}</div></div>`;
}

function runMarkup(run) {
  if (!run)
    return empty(
      "Waiting for investigation",
      "The worker will queue this captured incident automatically.",
    );
  let result;
  if (run.status === "failed") {
    result = `<div class="error-panel"><h4>${esc(label(run.error_code || "Investigation failed"))}</h4><p>${esc(run.error_detail?.message || "The model did not return a usable finding.")}</p>${run.error_detail?.fields ? `<ul>${run.error_detail.fields.map((field) => `<li><code>${esc(field.path)}</code>: ${esc(label(field.type))}</li>`).join("")}</ul>` : ""}<p class="mt-2">An operator can retry this investigation through the API.</p></div>`;
  } else if (run.finding) result = findingMarkup(run.finding);
  else
    result = empty(
      run.status === "queued" ? "Queued" : "Investigation running",
      "Tool activity updates here as results are recorded.",
    );
  return `<select id="attempt-select" class="form-select form-select-sm attempt-select" aria-label="Investigation attempt">${state.runs.map((attempt, index) => `<option value="${esc(attempt.investigation_id)}" ${run.investigation_id === attempt.investigation_id ? "selected" : ""}>${index === 0 ? "Latest" : "Earlier"} · ${esc(label(attempt.status))} · ${esc(attempt.investigation_id.slice(0, 8))}</option>`).join("")}</select><div class="run-summary">${badge(run.status)}<span>${esc(duration(run.duration_ms))}</span><span>${esc(run.usage?.requests ?? 0)} model requests</span><span>${esc(run.usage?.tool_calls ?? 0)} tool calls</span><span>${esc(((run.usage?.input_tokens || 0) + (run.usage?.output_tokens || 0)).toLocaleString())} reported tokens</span></div><div class="run-model mono">${esc(run.model_id)}<br>${esc(run.agent_version)} · ${esc(run.token_limit.toLocaleString())} token allowance</div>${result}`;
}

function renderDetail() {
  const incident = state.incident;
  if (!incident || document.activeElement?.id === "attempt-select") return;
  const metrics = incident.signal?.observed || {};
  byId("incident-detail").innerHTML =
    `<div class="detail-heading"><div><h2>${esc(incident.rule_id)}</h2><p class="mono">${esc(incident.incident_id)}</p></div>${badge(incident.status)}</div><div class="detail-metadata"><span>Topic <strong>${esc(incident.topic)}</strong></span><span>Producer <strong>${esc(incident.producer_id)}</strong></span>${incident.configuration_revision ? `<span>Revision <strong class="mono">${esc(incident.configuration_revision)}</strong></span>` : ""}<span>Contract <strong>${esc(incident.contract_id)} v${esc(incident.contract_version)}</strong></span><span>Fields <strong>${esc(incident.affected_fields.join(", "))}</strong></span>${typeof metrics.failure_ratio === "number" ? `<span>Captured failure <strong class="bad">${esc(percent(metrics.failure_ratio))}</strong></span>` : ""}</div><div class="detail-columns"><section><div class="section-heading"><h3>Activity timeline</h3><small>Recorded events · UTC</small></div><ol class="timeline">${timelineMarkup(incident, state.run)}</ol></section><section><div class="section-heading"><h3>Agent investigation</h3><button class="text-button" data-action="signal">View signal</button></div>${runMarkup(state.run)}</section></div>`;
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
    ? state.contracts
        .map(
          (contract) =>
            `<article class="contract-entry"><h3>${esc(contract.contract_id)} ${badge(`version ${contract.version}`)}</h3><p>${esc(contract.topic)} · Owner ${esc(contract.owner)} · Effective ${esc(formatTime(contract.effective_from))}</p>${contract.rules
              .map(
                (rule) =>
                  `<div class="contract-rule"><strong>${esc(rule.rule_id)}</strong> <span class="muted mono">${esc(rule.kind)}</span><dl><dt>Fields</dt><dd class="mono">${esc(rule.fields.join(", "))}</dd>${Object.entries(
                    rule.parameters,
                  )
                    .map(
                      ([key, value]) =>
                        `<dt>${esc(label(key))}</dt><dd class="mono">${esc(typeof value === "object" ? JSON.stringify(value) : value)}</dd>`,
                    )
                    .join("")}</dl></div>`,
              )
              .join("")}</article>`,
        )
        .join("")
    : empty(
        "No contract versions",
        "The configured topic has no recorded contract versions.",
      );
}

async function refreshEvents() {
  try {
    const events = await api("/api/events?limit=20");
    byId("events-body").innerHTML = events.length
      ? events
          .map(
            (event) =>
              `<tr><td class="mono">${esc(formatTime(event.ingested_at))}</td><td class="mono">${esc(rawInteger(event.event_time))}</td><td class="mono">r${esc(event.config_revision)}</td><td class="mono">${esc(event.partition)} / ${esc(event.kafka_offset)}</td><td class="mono">${esc(event.event_id)}</td></tr>`,
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
    "/api/producer/configuration",
    "/api/incidents?limit=20",
  ];
  const names = [
    "Stream",
    "Detection",
    "Investigation",
    "Configuration",
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
  const [stream, detection, investigator, configuration, incidents] = values;
  let throughput = null,
    failure = null;
  if (stream) {
    throughput = stream.recent_events / 10;
    setText("metric-throughput", throughput.toFixed(1), "mono");
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
    const results = detection.checks.map((check) => check.result);
    const result =
      results.find((check) => check.status === "violated") || results[0];
    setText("sidebar-topic", detection.topic);
    if (result) {
      const ratio = result.metrics?.failure_ratio;
      failure = typeof ratio === "number" ? ratio * 100 : null;
      setText(
        "metric-failure",
        ratio == null ? label(result.status) : percent(ratio),
        `${statusClass(result.status)} mono`,
      );
      setText(
        "metric-failure-detail",
        `${label(result.status)} · ${result.recent_samples} recent samples`,
      );
    } else setText("metric-failure-detail", "No evaluation recorded yet");
  }
  if (investigator) {
    setText(
      "configured-model",
      investigator.model_id || "Model metadata unavailable",
    );
    setText(
      "agent-version",
      `${investigator.agent_version || ""} · ${label(investigator.worker)}`,
    );
  }
  if (configuration) {
    state.configuration = configuration;
    renderConfiguration();
  }
  if (incidents) {
    state.incidents = incidents;
    renderIncidentList();
  }
  state.samples.push({ at: Date.now(), throughput, failure });
  if (state.samples.length > 60) state.samples.shift();
  chartRender();
  const errors = byId("source-errors");
  errors.hidden = state.errors.length === 0;
  errors.textContent = `${state.errors.join(" · ")}${state.errors.length ? ". Last successful values remain visible." : ""}`;
  const ok = state.errors.length === 0;
  setText(
    "poll-state",
    state.paused ? "Paused" : ok ? "Live · 5s" : "Some sources unavailable",
    !state.paused && ok ? "live-indicator" : "live-indicator paused",
  );
  setText(
    "last-updated",
    `Last poll ${formatTime(Date.now(), true)} UTC${ok ? "" : " · partial update"}`,
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
      stream: "Transport, throughput and timestamp health.",
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
    chartRender();
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
  const action = event.target.closest("[data-action]");
  if (action) inspectEvidence(action.dataset.action, action);
});
byId("incident-filter").addEventListener("change", renderIncidentList);
byId("history-button").addEventListener("click", async () => {
  try {
    showEvidence(
      "Producer configuration history",
      await api("/api/producer/configuration/history"),
      "Recorded revisions and operator changes",
    );
  } catch (error) {
    notify(error.message, true);
  }
});
byId("pause-button").addEventListener("click", () => {
  state.paused = !state.paused;
  clearTimeout(pollTimer);
  setText("pause-button", state.paused ? "Resume" : "Pause");
  byId("pause-button").setAttribute("aria-pressed", String(state.paused));
  if (state.paused) setText("poll-state", "Paused", "live-indicator paused");
  else tick();
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
window.addEventListener("resize", chartRender);
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
