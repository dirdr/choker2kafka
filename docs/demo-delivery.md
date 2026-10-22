# End-to-end demo delivery

The demo starts with a Git commit to the producer configuration. Sentinel applies the changed file as a new revision, captures the violation, investigates frozen evidence, and opens a constrained repair PR. After merge, fresh passing records establish recovery.

## Delivery order

- [x] Persist investigator model and token settings; apply them to new attempts.
- [x] Add the settings dialog and a consistent minimalist dark interface.
- [ ] Add `producer/config.json`, source provenance and GitHub synchronization.
- [ ] Show producer revision, configuration, source commit and GitHub links.
- [ ] Record short investigation explanations next to tool calls and results.
- [ ] Validate and persist a repair proposal against captured evidence and current source.
- [ ] Create one repair PR per proposal and persist its identity.
- [ ] Apply the merged file through synchronization and verify two fresh recovery windows.
- [ ] Reset demo records safely while excluding retained Kafka messages from the next run.
- [ ] Verify the deployed happy path and record a backup demo.

## Runtime configuration

The repository is `dirdr/choker2kafka`, the default branch is `main`, and the only writable producer file is `producer/config.json`. `GITHUB_TOKEN` stays in Runtime and needs Contents and Pull requests write access. No GitHub credentials are supplied to the model or browser.

Model and allowance changes are saved in PostgreSQL. Environment variables supply defaults until the first saved setting. Existing attempts keep their original model and limits. Dashboard access permits investigator settings changes; the browser route checks origin and a short-lived signed CSRF token. This is not user authentication. External settings writes require the operator bearer token.

Investigation explanations are concise, evidence-linked summaries of checks and results. They do not expose private chain-of-thought. Tool results remain inspectable.

A PR is a proposed repair. The incident remains open until the repaired revision produces fresh events that pass the captured contract. Opening a PR alone does not count as resolution.
