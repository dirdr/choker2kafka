# Incident identity

A new faulty producer configuration revision opens its own incident, even while an earlier revision's incident remains open. Repeated bad windows from the same revision reuse its open incident. Healthy revisions create no incidents.

The identity includes monitoring run, topic, producer, contract, rule, affected fields and configuration revision. A timestamp signal identifies the latest failing revision with at least 50 recent samples and strictly more than 80% failures within that revision. The existing overall-window and baseline requirements still apply. One new record cannot attribute a violation to a new revision, and a healthy revision cannot inherit an older revision's failures.

Every incident has its own frozen evidence. Migration `005_incident_revisions.sql` backfills older incident revisions from the failing event references in their original snapshots. It preserves those snapshots and investigation records. Unknown historical revisions remain nullable rather than being inferred from current configuration.

The investigation worker automatically queues one original attempt for each new incident. Existing failed attempts stay recorded; operators can retry through Bruno/API. Merely reading the workbench makes no model calls.

A successful finding is a diagnosis. Resolution still requires a repair and fresh passing data. The proposed next repair workflow is a reviewed producer-config pull request, followed by deployment and two verified recovery windows. Opening a PR alone will not resolve an incident. Fresh isolated replay is also pending; recorded tool history is not a new model run.
