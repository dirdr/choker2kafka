# Sentinel delivery checklist

Updated: 2026-10-22. Scope follows `sentinel-hackathon-plan.md` in the parent workspace. A checked implementation item means the code and its local checks are complete. Deployed verification has its own items.

## 1. Service connectivity — complete

- [x] Deploy one FastAPI application on Aiven Runtime with one HTTP port and one worker.
- [x] Keep `/health` independent of external dependencies.
- [x] Add concurrent Postgres, Kafka and Anthropic checks at `/ready` with HTTP 503 on failure.
- [x] Read the Kafka CA from `KAFKA_CA_CERT` without storing a certificate file in the image.
- [x] Accept multiline, escaped and flattened PEM values; return safe Kafka failure categories.
- [x] Verify deployed `/ready`: HTTP 200, all three dependencies `ok` on 2026-10-22.

Anthropic readiness validates authentication through the Models API. Inference credit, typed tools and structured output still need a separate smoke test in step 4.

## 2. Producer and ingestion — implemented; basic round trip confirmed

- [x] Separate event/configuration models, application orchestration, persistence, Kafka and HTTP adapters.
- [x] Apply versioned PostgreSQL migrations under a transaction advisory lock.
- [x] Persist producer configuration and append configuration history with revision checks.
- [x] Produce batches of ten synthetic orders, targeting ten events per second.
- [x] Reload committed configuration between batches; support milliseconds, seconds and microseconds.
- [x] Include event ID, producer ID, code version and configuration revision in each event.
- [x] Preserve raw business time, Kafka time/type, ingestion time and Kafka coordinates in PostgreSQL.
- [x] Deduplicate by event ID and Kafka coordinates; store malformed records separately.
- [x] Commit explicit Kafka offsets only after the database transaction succeeds.
- [x] Reconnect after failures and manage the worker through the FastAPI lifespan.
- [x] Expose bounded recent-event reads, stream freshness, configuration and history APIs.
- [x] Require an operator bearer token for configuration changes; reject stale revisions and unsupported fields.
- [x] Run local tests and lint checks for serialization, ingestion ordering, delivery errors, auth and shutdown.
- [ ] Run the PostgreSQL integration suite against a dedicated TLS-enabled test database.
- [x] Observe event rows in PostgreSQL after running the producer/ingestion slice; confirmed by the operator.
- [ ] Measure the deployed event rate through the stream API.
- [ ] Change the timestamp unit through the protected API and verify new Kafka records carry the new revision.
- [ ] Restart the deployed app and verify configuration history and duplicate-safe ingestion persist.

The operator confirmed the basic round trip and authorized the detection slice. Rate, configuration-change and deployed restart checks remain open.

## 3. Timestamp detection and incident capture — implemented; deployed verification pending

- [x] Persist declarative contract versions, producer context and labelled synthetic consumer expectations.
- [x] Register pure detectors by rule kind; implement `timestamp_bounds` only.
- [x] Evaluate every five seconds using adjacent ten-second recent and sixty-second baseline windows.
- [x] Require 50 recent integer samples and 100 baseline samples; distinguish warm-up and stale transport.
- [x] Select each event's effective contract by ingestion time; retain the triggering version in the signal.
- [x] Signal when strictly more than 80% of recent timestamps violate their effective contracts.
- [x] Include failure ratios, scale changes, plausible conversions and evidence references.
- [x] Capture bounded source snapshots and atomically create incidents and a detection timeline entry.
- [x] Freeze event windows, contracts, profiles, configuration history and available consumer context; report missing configuration revisions.
- [x] Protect source versions, snapshots and timeline entries from updates/deletes through database triggers.
- [x] Persist monitoring run identity and suppress duplicate active episodes across restarts.
- [x] Expose contract, detection, incident and frozen-evidence read APIs.
- [x] Test pure rules, API validation and lifecycle; validate repository SQL in isolated embedded PostgreSQL.
- [x] Document architecture, database records, contract definitions and live verification.
- [x] Add a Bruno collection with Local/Aiven environments, read checks, frozen-evidence reads and revision-aware producer controls.
- [x] Verify a deployed healthy baseline and automatically captured seconds violation.
- [ ] Verify a live microseconds violation separately.
- [ ] Verify repeated bad windows and a restart retain one active incident and its original evidence.
- [ ] Verify a live unit restoration changes new checks without rewriting the incident snapshot.
- [ ] Verify stale transport suppresses new incidents on the deployed stack.

Eligible-memory retrieval and capture remain part of the later investigation/memory slice. Current snapshots explicitly mark memory capture as not implemented. Investigation is implemented separately in step 4; proposals, repairs and automatic resolution remain pending.

## 4. Agent investigation — implemented; deployed verification pending

- [x] Pin one Claude model after a real typed-tool and structured-output smoke test.
- [x] Add frozen-evidence and producer-context tools; expose reviewed-memory unavailability explicitly.
- [ ] Implement reviewed eligible-memory retrieval and capture.
- [x] Queue original investigations automatically and preserve failures across restarts; protect explicit retries with operator authentication.
- [x] Persist tool starts/results during execution so the workbench can poll live activity.
- [x] Keep live polling compact; allow explicit access to raw tool bodies.
- [x] Require strict structured output, allow one bounded correction and save safe validation details.
- [x] Configure the Claude model through `ANTHROPIC_MODEL` and expose configured/actual model metadata.
- [x] Observe deployed tool calls and a saved failure; reproduce and fix malformed output using the real captured incident.
- [x] Validate run SQL, retry isolation and append-only tool activity in embedded PostgreSQL.
- [ ] Redeploy and verify a live incident progresses from queued to a recorded finding with actual tool activity.
- [x] Persist investigations, tool activity, findings, failures and usage.
- [x] Enforce ten tool calls, a token allowance and a 45-second deadline.
- [x] Validate evidence references and abstain when attribution is unsupported.

## 5. Policy-controlled remediation and recovery — pending

- [ ] Persist exact proposals with evidence and expected contract/configuration revisions.
- [ ] Validate writable targets and fields; preview serialization against the captured contract.
- [ ] Default to Approval required; persist approvals, rejections and mode changes.
- [ ] Execute authorized proposals through one revision-checked, idempotent path.
- [ ] Prevent mode changes from silently executing pending proposals.
- [ ] Require two passing, fresh, non-overlapping ten-second recovery windows from the repaired revision.
- [ ] Persist recovery evidence before resolving an incident.
- [ ] Retrieve only reviewed or verified, compatible, unexpired incident memory.

## 6. Workbench and re-investigation — workbench implemented; deployed verification pending

- [x] Serve pinned Tabler assets, Jinja templates and polling handlers from this application.
- [x] Show incident lists, recorded evidence, attempts, findings, stream records and contract versions.
- [ ] Add configuration diffs, policy decisions and recovery history after their backend is implemented.
- [x] Display the configured model and each run's actual model.
- [ ] Add an authenticated model selector if time permits; Runtime model configuration already works.
- [x] Display original investigation tool activity, status, duration and findings through compact polling.
- [x] Keep manual producer changes and paid retries in Bruno/API; the workbench is read-only and uses no operator token.
- [x] Verify frontend behavior through API and DOM checks; add a pinned Playwright fixture/live harness.
- [ ] Verify desktop/mobile rendering with Playwright outside the sandbox launch restriction.
- [ ] Redeploy and test the workbench against the live captured incident.
- [ ] Reuse the activity view for fresh isolated re-investigation calls without exposing private chain-of-thought.
- [ ] Provide operator approval/rejection controls and safe timestamp rendering.
- [ ] Re-investigate resolved incidents from captured source context in a separate run.
- [ ] Prove re-investigation cannot mutate live configuration or change resolution counts.
- [ ] Settle whether original outcomes are visible to the re-investigation agent before claiming a blinded comparison.

## 7. Grafana, evaluation and demo — pending

- [ ] Connect existing Grafana through restricted PostgreSQL views and a read-only account.
- [ ] Export the dashboard and save a screenshot; limit setup to twenty minutes.
- [ ] Run all seven fixture cases from plan section 10 against a deterministic baseline.
- [ ] Exercise both execution modes, rejected/stale actions, redelivery, restarts and replay isolation.
- [ ] Record measured latency, tool usage, action outcomes, recovery and failures; export results.
- [ ] Save a resolved incident, a backup recording and the three-minute pitch.
- [ ] Freeze features before final rehearsal; consider Slack only after the core and backup are complete.

## Running and verifying the current slice

Keep `DATABASE_URL`, `KAFKA_BOOTSTRAP_SERVERS`, `KAFKA_SECURITY_PROTOCOL`, `KAFKA_SASL_MECHANISM`, `KAFKA_SASL_USERNAME`, `KAFKA_SASL_PASSWORD`, `KAFKA_CA_CERT` and `ANTHROPIC_API_KEY` for the Runtime SASL setup. No Kafka certificate file is shipped. Optional settings now read by the application:

| Variable | Default | Purpose |
|---|---|---|
| `KAFKA_TOPIC` | `orders` | Topic to create if absent, produce to and consume from |
| `KAFKA_GROUP_ID` | `sentinel-orders-v1` | Stable consumer group across restarts |
| `STREAM_ENABLED` | `true` | Set to `false` to disable the stream worker |
| `DETECTION_ENABLED` | `true` | Set to `false` to disable detection independently of ingestion |
| `INVESTIGATION_ENABLED` | `true` | Disable automatic model investigations independently of detection |
| `ANTHROPIC_MODEL` | `claude-haiku-4-5-20251001` | Claude model for new attempts; recorded per run |
| `INVESTIGATION_TOKEN_LIMIT` | `20000` | Per-attempt token budget, 4000–100000; includes a 1500-token output reserve |
| `CODE_VERSION` | `0.1.0` | Producer build identifier recorded in events |
| `OPERATOR_TOKEN` | unset | Required for configuration mutation; reads and streaming work without it |

Keep one Runtime instance and one Uvicorn worker. Run locally with:

```sh
uv sync --locked
uv run uvicorn sentinel.main:app --reload --port 8080
```

The stream starts automatically, applies migrations and creates the configured topic if needed. It retries dependency failures while `/health` remains available. The independent detector seeds the configured topic's demo contract/context, retains its monitoring run and evaluates fresh database windows. `/ready` checks dependency connectivity; `/api/stream` reports ingestion state and `/api/detection` reports rule evaluations.

| Endpoint | Purpose |
|---|---|
| `GET /api/stream` | Worker state, last ingestion time and recent event count |
| `GET /api/events?limit=20` | Recent events, bounded to 100 |
| `GET /api/producer/configuration` | Current unit and revision |
| `GET /api/producer/configuration/history` | Latest 100 configuration revisions |
| `PATCH /api/producer/configuration` | Change the unit with an operator bearer token |
| `GET /api/contracts` | Declarative contract versions for the configured topic |
| `GET /api/detection` | Detector worker state and latest persisted rule evaluations |
| `GET /api/incidents?limit=20` | Incident summaries, bounded to 100; optional `status=open` filter |
| `GET /api/incidents/{id}` | Recorded signal and timeline |
| `GET /api/incidents/{id}/evidence` | Immutable captured source snapshot |
| `GET /api/investigation` | Investigation worker status |
| `GET /api/incidents/{id}/investigations` | Latest 100 investigation attempts |
| `GET /api/investigations/{id}` | Run state, finding, usage and live tool activity |
| `POST /api/incidents/{id}/investigations/retry` | Authenticated retry of a failed attempt on an open incident |

The patch body contains `expected_revision`, `event_time_unit` and `reason`. Use the revision returned by the configuration endpoint. A stale revision returns HTTP 409; malformed or unsupported changes return HTTP 422. This is an operator configuration API; agent proposals, approval policy and recovery are still pending in step 5.

Run tests with `uv run python -m unittest discover -s tests -v`. Set `TEST_DATABASE_URL` to a dedicated TLS-enabled PostgreSQL test database to include integration tests; those tests apply migrations, change test producer configuration and retain append-only evidence. They are skipped when that variable is absent. Do not point the integration suite at the running demo database.

Current local result: 97 unit/API tests passed; twenty-two network integration tests are skipped without `TEST_DATABASE_URL`. Those twenty-two repository test cases also passed against isolated embedded PostgreSQL through a temporary test adapter, validating migrations, SQL, transactions, deduplication, restart identity and evidence immutability. This does not validate psycopg/TLS/network behavior against Aiven. The native PostgreSQL test server was blocked by sandbox shared-memory permissions. Lint, formatting and lockfile checks passed.

See [the architecture views](docs/architecture/index.md), [the table inventory](docs/architecture/data-model.md) and [contract definitions/live verification](docs/contracts.md). The next implementation slice is proposal/approval policy and deterministic recovery after live investigation verification.

Investigation smoke: real Anthropic calls using the production Pydantic AI agent and pinned `claude-haiku-4-5-20251001` returned a validated finding after all three tools. The synthetic run used two inference requests, 11,294 input tokens and 1,032 output tokens. A temporary HTTP transport relayed the actual SDK requests through curl because sandboxed Python cannot access external networking; deployed SDK networking remains to be verified. SDK versions are pinned after finding an incompatibility with Anthropic 2.x.

Live investigation hardening: a captured seconds incident reproduced a malformed structured result (array field encoded as text, required fields missing). Strict output plus one bounded correction and a smaller labelled sample passed a real model run against that frozen incident: two requests, 9,360 input tokens and 710 output tokens. Deployed confirmation of this patch remains pending. The submission deliverables and demo journey are mapped in [the submission plan](docs/submission.md).

The workbench is available at `/` after redeployment, with direct incident links at `/incidents/{id}`. See [workbench deployment and checks](docs/workbench.md). The operator requested the frontend before the remediation slice; manual changes stay in Bruno/API, while PR-based repair, verified recovery and replay remain pending.

## Latest operator feedback

- [x] Open one incident per faulty configuration revision, with per-revision sample checks and immutable evidence.
- [x] Keep the home page focused on incident summaries; open details only on selection.
- [x] Move stream graphs to `/stream` and contract definitions to `/contracts`.
- [x] Make the workbench read-only; use Bruno/API for producer changes and paid retries.
- [ ] Add true isolated replay with fresh model calls; historical tool activity is already visible.
- [ ] Implement the agreed producer-config PR workflow and resolve only after merge/deployment and fresh recovery proof.

- [x] Darken the workbench and increase text sizes with a self-hosted Inter font.

The next repair slice is specified in [the producer PR workflow](docs/producer-repair.md). A database-only Bruno fault does not create a file diff: the PR demonstration must introduce the fault in the versioned producer config and apply it through deployment. A PR is a proposed repair; only verified new data establishes resolution.

## Demo readiness — next steps

- [x] Fix the default Anthropic SDK client retry argument and cover the production client path with a regression test.
- [ ] Redeploy the SDK fix, retry the existing failed incident through Bruno, and verify a persisted finding on the workbench.
- [ ] Preserve one verified demo incident and its frozen evidence; defer historical cleanup until that example succeeds.
- [ ] Add isolated replay for successful attempts, with fresh model calls and no producer writes.
- [ ] Add versioned producer configuration and deployment synchronization; producer changes currently use the database API.
- [ ] Implement a constrained producer repair PR, followed by merge/deployment and verified recovery.

The retry endpoint already accepts failed attempts on open incidents. The dashboard displays attempts but remains read-only. Model selection currently uses `ANTHROPIC_MODEL` in Runtime environment settings and requires an application restart or redeployment; a dashboard model selector is not implemented.
