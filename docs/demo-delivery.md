# End-to-end demo delivery

The demo starts with a Git commit to the producer configuration. Sentinel applies the changed file as a new revision, captures the violation, investigates frozen evidence, and opens a constrained repair PR. After merge, fresh passing records establish recovery.

## Delivery order

- [x] Persist investigator model and token settings; apply them to new attempts.
- [x] Add the settings dialog and a consistent minimalist dark interface.
- [x] Add `producer/config.json`, source provenance and GitHub synchronization.
- [x] Show producer revision, configuration, source commit and GitHub links.
- [x] Record short investigation explanations next to tool calls and results.
- [x] Validate and persist a repair proposal against captured evidence and current source.
- [x] Implement idempotent repair PR creation and persist its identity; real GitHub verification remains pending.
- [x] Implement merged-file synchronization and two-window recovery; verify on the deployment next.
- [x] Implement one-time startup reset with durable Kafka ingestion boundaries; deployed reset remains pending.
- [x] Verify the deployed happy path: revision 7 → supported finding → PR #1 → merged revision 8 → two passing recovery windows → resolved.
- [ ] Record the backup MP4 and verify the clean-start reset on the deployment.

## Runtime configuration

The repository is `dirdr/choker2kafka`, the default branch is `main`, and the only writable producer file is `producer/config.json`. `GITHUB_TOKEN` stays in Runtime and needs Contents and Pull requests write access. No GitHub credentials are supplied to the model or browser.

Model and allowance changes are saved in PostgreSQL. Environment variables supply defaults until the first saved setting. Existing attempts keep their original model and limits. Dashboard access permits investigator settings changes; the browser route checks origin and a short-lived signed CSRF token. This is not user authentication. External settings writes require the operator bearer token.

Investigation explanations are concise, evidence-linked summaries of checks and results. They do not expose private chain-of-thought. Tool results remain inspectable.

A PR is a proposed repair. The incident remains open until the repaired revision produces fresh events that pass the captured contract. Opening a PR alone does not count as resolution.

## Clean deployment

Set `DEMO_RESET_ID=demo-2026-10-22-1` for the requested clean run, keep the producer file healthy, and deploy the latest commit. Reset runs before workers start. It clears demo stream, incident, investigation, repair and contract records; preserves application settings and reset receipts; restores the healthy producer baseline; and rejects retained Kafka offsets through database triggers. Reusing the same reset ID on later deployments does not delete the next run. A new reset ID requests another reset. Existing open repair PRs must be closed or merged first.

Check `/api/demo` for the reset receipt and open-incident count, `/api/producers` for source sync, and `/api/repair` for the repair worker. See [the narration](demo-script.md), [the pitch slide](submission-slide.md), and [the evidence exporter](evidence-export.md).
