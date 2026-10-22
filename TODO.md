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

## 2. Producer and ingestion — current slice

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
- [ ] Redeploy this slice and verify events flow from Kafka into PostgreSQL at the expected rate.
- [ ] Change the timestamp unit through the protected API and verify new Kafka records carry the new revision.
- [ ] Restart the deployed app and verify configuration history and duplicate-safe ingestion persist.

Finish these verification items before building the detector.

## 3. Timestamp detection and incident capture — next

- [ ] Persist versioned timestamp contracts, producer context and consumer expectations.
- [ ] Evaluate every five seconds using adjacent ten-second recent and sixty-second baseline windows.
- [ ] Require 50 recent integer samples and 100 baseline samples; distinguish warm-up and stale transport.
- [ ] Signal when more than 80% of recent timestamps violate the effective contract.
- [ ] Include scale changes, plausible conversions and evidence references.
- [ ] Capture bounded immutable source snapshots and create incidents automatically.
- [ ] Suppress duplicate incidents for the same active episode.
- [ ] Expose incident and evidence APIs with freshness and source provenance.

## 4. Agent investigation — pending

- [ ] Pin one Claude model after a real typed-tool and structured-output smoke test.
- [ ] Add bounded evidence, producer-context and eligible-memory tools.
- [ ] Persist investigations, tool activity, findings, failures and usage.
- [ ] Enforce ten tool calls, a token allowance and a 45-second deadline.
- [ ] Validate evidence references and abstain when attribution is unsupported.

## 5. Policy-controlled remediation and recovery — pending

- [ ] Persist exact proposals with evidence and expected contract/configuration revisions.
- [ ] Validate writable targets and fields; preview serialization against the captured contract.
- [ ] Default to Approval required; persist approvals, rejections and mode changes.
- [ ] Execute authorized proposals through one revision-checked, idempotent path.
- [ ] Prevent mode changes from silently executing pending proposals.
- [ ] Require two passing, fresh, non-overlapping ten-second recovery windows from the repaired revision.
- [ ] Persist recovery evidence before resolving an incident.
- [ ] Retrieve only reviewed or verified, compatible, unexpired incident memory.

## 6. Workbench and re-investigation — pending

- [ ] Serve pinned Tabler assets, Jinja templates and polling handlers from this application.
- [ ] Show incidents, evidence, findings, configuration diffs, decisions and recovery history.
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
| `CODE_VERSION` | `0.1.0` | Producer build identifier recorded in events |
| `OPERATOR_TOKEN` | unset | Required for configuration mutation; reads and streaming work without it |

Keep one Runtime instance and one Uvicorn worker. Run locally with:

```sh
uv sync --locked
uv run uvicorn sentinel.main:app --reload --port 8080
```

The stream starts automatically, applies migrations and creates the configured topic if needed. It retries dependency failures while `/health` remains available. `/ready` checks dependency connectivity; `/api/stream` reports worker state and transport freshness.

| Endpoint | Purpose |
|---|---|
| `GET /api/stream` | Worker state, last ingestion time and recent event count |
| `GET /api/events?limit=20` | Recent events, bounded to 100 |
| `GET /api/producer/configuration` | Current unit and revision |
| `GET /api/producer/configuration/history` | Latest 100 configuration revisions |
| `PATCH /api/producer/configuration` | Change the unit with an operator bearer token |

The patch body contains `expected_revision`, `event_time_unit` and `reason`. Use the revision returned by the configuration endpoint. A stale revision returns HTTP 409; malformed or unsupported changes return HTTP 422. This is an operator configuration API; agent proposals, approval policy and recovery are still pending in step 5.

Run tests with `uv run python -m unittest discover -s tests -v`. Set `TEST_DATABASE_URL` to a dedicated TLS-enabled PostgreSQL test database to include integration tests; those tests apply migrations and change the test producer configuration. They are skipped when that variable is absent.

Current local result: 42 tests passed; five PostgreSQL integration tests skipped. Lint, formatting and lockfile checks passed. This environment could not resolve the PostgreSQL hostname, so the live database tests and deployed stream checks remain open.
