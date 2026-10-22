# Producer repair through a pull request

The Git-backed producer and PR repair journey is implemented and verified on the deployment. Incident `3f879fa2-bea9-45ec-840e-3a3612d55e7c` captured revision 7, obtained a supported finding, opened PR #1, and resolved after merged revision 8 passed two recovery windows.

## Runtime setup

Set `GITHUB_TOKEN` with repository Contents and Pull requests write permissions. `GITHUB_REPOSITORY` defaults to `dirdr/choker2kafka`; `GITHUB_BRANCH` defaults to `main`. The adapter writes only `producer/config.json`. It never merges a PR.

The source worker reads a specific Git commit every ten seconds and applies the configuration transactionally. A changed file creates a new producer revision with file and commit provenance. Unrelated commits leave the revision unchanged. Reverting to a previously used configuration creates a new revision. Events carry the applied source commit as their code version.

Without GitHub credentials, the packaged file supplies a local configuration once per worker startup. GitHub watching and PR creation are reported as unavailable.

## Demo journey

1. Start with milliseconds in the producer file and a healthy stream.
2. Change the file to seconds in GitHub and commit directly to `main`.
3. Watch `/producers` for the new revision and source commit. No application redeployment is required for a watched file change.
4. Open the captured incident and follow its tool checks, finding and evidence references.
5. Inspect the generated repair PR. The proposed unit comes from the frozen contract, not a free-form model command.
6. Review and merge the PR in GitHub.
7. Wait for source synchronization and two fresh, non-overlapping ten-second windows with at least 50 passing events each from the repaired revision. Only then does Sentinel resolve the incident.

The adapter checks the runtime revision, current contract, repository and file SHA. A stale source or unsupported finding cannot create a repair. Deterministic branches and PR lookup prevent duplicate PRs after ambiguous network failures. Proposal, PR identity and recovery evidence are retained in PostgreSQL.

`/api/producers` reports source synchronization. `/api/repair` reports the worker. `/api/incidents/{id}/repair` returns the proposal, PR and latest recovery evidence.

Opening or merging a PR alone does not resolve an incident. Recovery requires the repaired source to be applied and fresh data to satisfy the contract. Manual database-only faults do not fabricate Git diffs.

For a clean run, see [the demo reset instructions](demo-delivery.md). Capture submission evidence before clearing a successful incident. GitHub's [contents API](https://docs.github.com/en/rest/repos/contents) and [pull-request API](https://docs.github.com/en/rest/pulls/pulls) document the repository operations used by the adapter.
