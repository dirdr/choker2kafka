# Sentinel demo script

Target length: three minutes. Rehearse against the deployed journey before recording. If you shorten waiting periods in the edit, label them and retain the actual measured timings in the evidence report.

## 0:00–0:20 · The problem

For data platform teams, a valid Kafka message can still carry bad data. A timestamp can remain an integer while changing from milliseconds to seconds. Schema validation accepts it, but downstream calculations can become wrong.

Sentinel connects the contract breach to the producer change and helps the team review a repair.

## 0:20–0:40 · Start healthy

Here is our producer and its configuration in GitHub. It currently emits timestamps in milliseconds, as the contract expects. Events are flowing, and there are no open incidents.

The producer revision and source commit tell us which configuration produced each event.

## 0:40–1:05 · Introduce the fault

I’ll change the configuration to seconds and commit it directly in GitHub.

Sentinel watches that file and applies the changed configuration as a new producer revision. We do not need to call an API or redeploy for this change.

The messages still pass the integer type check. Sentinel detects that their values violate the contract and captures an incident.

## 1:05–1:45 · Investigate the evidence

The incident freezes the failing events, contract version and configuration history. The agent investigates that snapshot, so later changes cannot rewrite its evidence.

We can see each tool call, what it checks, and the result it returns. The agent compares the event sample with the contract, then links the affected revision to its captured configuration.

Its finding cites the evidence behind the diagnosis: this revision emits seconds where the contract requires milliseconds. It also considers alternative explanations and states its confidence.

## 1:45–2:15 · Review the repair

Sentinel opens a pull request changing the producer configuration back to the required unit.

The repair changes one allowed field. It does not weaken the contract to make the failure disappear.

An engineer reviews and merges the PR. Sentinel does not merge it automatically.

## 2:15–2:40 · Prove recovery

Sentinel picks up the merged file and applies a new producer revision.

The incident remains open while fresh events arrive. Only after two separate passing windows does Sentinel record recovery evidence and resolve it.

A proposed fix is useful. Verified recovery is the outcome.

## 2:40–3:00 · The value

Aiven Kafka carries the events. Aiven PostgreSQL stores the contracts, revisions, frozen evidence, investigation activity and recovery proof. The agent reads that data through typed tools.

For the on-call team, Sentinel turns a contract breach into an evidence-backed diagnosis, a reviewable repair, and proof that the stream is trustworthy again.
