# Producer repair through a pull request

This is the next implementation slice. PR creation, file-driven configuration sync and verified resolution are not implemented yet. The current workbench is read-only; Bruno/API provide operator controls.

## Target journey

1. Keep the demo producer configuration in `producer/config.json` in this repository.
2. A deliberate file change to seconds or microseconds is committed, pushed and deployed.
3. The producer applies the changed file to PostgreSQL through the existing revision-checked configuration service. New events carry the resulting revision and source commit.
4. A violation captures its own revision and immutable evidence. Claude produces a supported finding and a proposed correction.
5. Sentinel opens a PR changing only the allowed producer configuration field back to the unit required by the captured contract. It records the branch, file SHA, commit and PR URL against the incident.
6. An engineer reviews and merges in GitHub. Deployment applies that new file version to PostgreSQL and starts emitting events from the repaired revision.
7. Two fresh, non-overlapping ten-second windows, each with at least 50 events from the repaired revision, must pass the active contract before Sentinel records recovery and resolves the incident.

Opening or merging a PR is not proof of recovery. The dashboard should show the finding, proposed diff, PR link, deployment state and fresh-data checks. It should not expose producer fault controls.

## Configuration source

The file can remain small:

```json
{
  "producer_id": "checkout",
  "event_time_unit": "milliseconds"
}
```

PostgreSQL owns the runtime revision counter; Git owns the desired configuration. Persist the last applied file hash and source commit. Apply a file change once, in the same transaction as the configuration/history write. Compare with the last applied hash rather than rejecting every hash seen before, so reverting to a previous healthy value still applies correctly. Unrelated application deployments must not create new producer revisions.

The producer folder and configuration must be included in the container build. A pushed commit changes PostgreSQL only after the configured deployment or reconciliation step runs; pushing a file alone does not update the running producer.

Bruno changes currently affect the database directly. They do not change a repository file. If Git already contains milliseconds while the database emits seconds, a PR that merely sets milliseconds would have no real diff. The full PR demonstration must introduce the fault in the versioned file, or report configuration drift and reapply the committed desired configuration. It must not fabricate a repair diff.

## GitHub adapter

The Runtime app can create a branch, update the configuration file and open a PR through GitHub's REST API. It does not need a local Git checkout or the GitHub CLI. A repository-scoped fine-grained token is the simplest demo credential; a GitHub App is the longer-term option. Runtime needs credentials with Contents write and Pull requests write for this repository. Credentials stay server-side.

The adapter must accept a validated proposal, not arbitrary model-authored file paths. Restrict writes to `producer/config.json` and the producer's `event_time_unit`. Require a supported contract unit, captured evidence IDs, the expected runtime revision and expected repository file SHA. A stale file or runtime revision requires a new proposal.

Use a deterministic branch per proposal and persist the PR identity. Repeated worker attempts must find the existing branch/commit/PR rather than create duplicates. The app must not merge automatically in the initial workflow. Older incident revisions remain recorded; a stale diagnosis must not overwrite a newer producer configuration.

See [GitHub's pull-request API](https://docs.github.com/en/rest/pulls/pulls#create-a-pull-request) and [installation authentication](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/authenticating-as-a-github-app-installation).

## Delivery order

- [ ] Add the producer file and an idempotent, revision-checked sync path with source provenance.
- [ ] Validate and persist exact repair proposals and stale-state failures.
- [ ] Add the restricted GitHub adapter and durable branch/PR records.
- [ ] Configure repository credentials in Runtime and verify one real PR.
- [ ] Observe merge/deployment and link new event revisions to the applied proposal.
- [ ] Persist two passing recovery windows before resolving.
- [ ] Display the PR and recovery records in the read-only workbench.
- [ ] Add isolated replay as a new model run over frozen evidence, with no producer or GitHub writes.
