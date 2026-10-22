# Captured-incident investigation

An open incident is automatically queued once. A separate worker claims it, reads its immutable snapshot and runs Pydantic AI against direct Anthropic with the Claude model configured by `ANTHROPIC_MODEL` (default `claude-haiku-4-5-20251001`). Healthy traffic creates no incidents and makes no investigation calls.

The agent has three read tools: `inspect_incident`, `lookup_producer_context` and `find_prior_incidents`. The first exposes the captured evaluation, contract versions and a labelled sample of the first five and last five captured events. The second exposes captured configuration history and declared consumer expectations. The memory tool explicitly reports that reviewed-memory retrieval is not implemented. None reads current configuration or mutates the producer.

The output tool requests strict JSON schema compliance. Findings contain likely cause, alternatives, consumer expectations, recommendation, confidence rationale, evidence IDs and optional producer/revision attribution. References must have been returned by tools. Attribution requires a captured configuration revision, an event carrying that revision and a referenced contract. Missing/truncated attribution context requires abstention. These checks establish reference integrity; they do not prove every natural-language conclusion. Consumer expectations describe potential impact, not a measured downstream outage.

Each attempt has a configurable model/tool deadline (`INVESTIGATION_DEADLINE_SECONDS`, default 120, range 30–300), ten successful tool calls, six inference requests, zero automatic SDK/tool retries and one structured-output correction attempt within the same limits and a configurable token allowance (`INVESTIGATION_TOKEN_LIMIT`, default 50000, range 4000–100000). Token counting precedes each inference request. A 3000-token reserve and a matching per-response output cap prevent an accepted request from exceeding the configured allowance; runs can stop conservatively before consuming the whole allowance. Usage returned before a failure is saved; a request interrupted before usage is returned can have unreported billed tokens.

`GET /api/incidents/{id}/investigations` lists attempts. `GET /api/investigations/{id}` exposes queued/running/completed/failed state, compact tool-start/result summaries, finding, usage, duration and safe error details. Poll it while the run is active. Append `?include_activity_bodies=true` only when you need full archived tool bodies. Output validation failures identify affected field names and error types without exposing raw model output. A tool start commits before reading; its result commits before returning to Claude. Private model chain-of-thought and raw message history are not stored. The workbench renders this live activity and evidence-backed explanation. Isolated re-investigation remains pending and will execute fresh model calls against the original sources.

Failures remain visible and are not automatically charged again. A running attempt abandoned for over 90 seconds becomes a retryable `interrupted` failure. With the worker enabled, `POST /api/incidents/{id}/investigations/retry` and an operator bearer token append a new queued attempt only when the latest attempt failed and the incident remains open. Concurrent duplicate retries are rejected. Earlier findings and source snapshots remain intact. Recommendations do not execute repairs or resolve incidents.

The worker defaults to enabled. Set `INVESTIGATION_ENABLED=false` to stop automatic investigations. Keep `ANTHROPIC_API_KEY` in Runtime; no additional credentials are needed. One Runtime instance and one Uvicorn worker remain the supported topology. On deployment, migration `003_investigation.sql` creates run and append-only activity records.

For live verification, establish a healthy detector baseline, change the producer to seconds through Bruno, wait for capture, list investigations and poll the run detail. Expect real tool activity followed by a finding or explicit retryable failure. Restore milliseconds through the operator API. The incident remains open until the later recovery slice is implemented.

`GET /api/investigation` exposes the current configured model/provider, agent version and limits for dashboard display. `ANTHROPIC_MODEL` is an Anthropic Claude ID; changing the Runtime variable requires redeployment and affects newly queued attempts and explicit retries. Existing attempts retain their model IDs and token allowances. Queued work is stamped with the implementation version when claimed. A dashboard model selector remains pending.


Retry budgets can be changed without redeploying. Send an optional JSON body to `POST /api/incidents/{id}/investigations/retry` with `token_limit` (4000–100000) and `deadline_seconds` (30–300). Omitted fields use Runtime defaults. Authentication and the failed-attempt/open-incident checks still apply. Each new attempt records its own limits; previous attempts keep theirs. Saved application settings override Runtime model/token defaults. Changes in the dashboard apply to new attempts without a restart. The deadline remains an environment default or a per-retry override. Existing queued attempts retain their saved budget.

```json
{"token_limit": 80000, "deadline_seconds": 240}
```

A larger budget permits more work but does not guarantee a supported finding. Request and tool-call limits remain six and ten. Abandoned runs are recovered only after their recorded deadline plus 45 seconds.
