# Hackathon submission plan

The submission should tell one story: a Kafka timestamp regression is detected, investigated from captured data, repaired through approval, and resolved only after fresh events prove recovery. This is the target demonstration. Current code supports detection, capture, investigation and the first workbench. Approval, execution and verified recovery remain to be implemented.

## Required deliverables

| Field | Proposed submission | Purpose |
|---|---|---|
| Project name | **Sentinel** | Keep the product name consistent across UI, slide and video |
| One-line pitch | **Sentinel turns Kafka contract violations into evidence-backed investigations and verified repairs.** | Explain the result in one sentence |
| Three-minute demo | An MP4 showing one timestamp regression from healthy stream through approved repair and fresh-data recovery | Prove one working end-to-end customer journey |
| The data layer in action | Written explanation of the Kafka → PostgreSQL evidence → Claude tools → controlled configuration change → Kafka recovery loop | Explain what the agent knows and how it can support its conclusions |
| Evidence it works | A compact PDF with before/after evidence and measured results across the seven planned cases, accompanied by exported machine-readable results if the form permits | Demonstrate correctness, limits and value beyond a timestamp-only diagnosis |
| One pitch slide | One landscape slide combining customer/problem, journey, architecture strip, measured proof, why now and first-user strategy | Carry the entire stage pitch; use a public view-only link |

## The customer and product story

Target the platform engineer responsible for Kafka producers and data contracts. A producer can change timestamp units while its events still pass integer-schema validation. Engineers must determine what changed, which records and consumers are affected, and whether a proposed correction actually worked.

The demonstration scenario is one concrete contract violation, not a claim that all stream problems are solved. Declarative versioned contracts and separate detector/action boundaries provide the extension path; timestamp-unit checks and the controlled producer are the implemented scope.

Suggested opening: “The schema is valid, but the data is wrong. Sentinel connects the broken records to the producer change, proposes a correction with evidence, and checks new traffic before calling the incident resolved.”

## Three-minute MP4 storyboard

Warm the healthy baseline before recording. Show the application workbench at readable scale, with the selected model visible. Use Bruno as a setup/debugging aid rather than making raw JSON the main product experience.

| Time | What the viewer sees | What to explain |
|---|---|---|
| 0:00–0:15 | Healthy stream, contract expects milliseconds, producer revision and model badge | Who the engineer is and why schema validation missed this class of problem |
| 0:15–0:35 | Change producer to seconds; live failure ratio rises and one incident appears | An actual configuration change affects actual Kafka events; capture is automatic |
| 0:35–1:15 | Incident timeline shows real tool starts/results; expand one evidence item | Claude reads frozen records, contract versions, configuration history and declared consumer expectations |
| 1:15–1:45 | Finding, cited evidence and proposed revision-checked diff | Explain the unit regression, a competing explanation and expected consumer impact; distinguish declared expectations from observed outages |
| 1:45–2:20 | Approve the exact proposal; new events carry the repaired revision; two recovery windows pass | Approval controls the write; deterministic checks establish recovery |
| 2:20–2:40 | Resolved incident, preserved timeline, passing fresh data and measured timings | This is a recorded incident with proof, not a prewritten success message |
| 2:40–3:00 | One compact data-flow/evidence view and the closing value statement | Summarize data grounding, measured baseline comparison and the first-user audience |

Show genuine elapsed progress. If editing removes waiting time, label the cut; do not claim the edited duration as system latency. Save an uncut run with timestamps as supporting evidence. Use real measured latency in the final narration after rehearsal.

Isolated re-investigation remains a planned feature. Demonstrate it separately in supporting evidence or a backup recording once implemented. Do not displace the repair-and-recovery journey to fit a second full model run into three minutes.

## Written data-layer explanation

Draft to adapt after the full journey is implemented:

“Sentinel consumes a controlled orders stream from Aiven Kafka. Events carry producer identity, build version and configuration revision. PostgreSQL preserves the raw business timestamp, Kafka coordinates/time and ingestion time, together with versioned contracts, configuration history and declared consumer expectations. Deterministic checks evaluate records against the contract effective at ingestion. A violation freezes the relevant source context in an immutable incident snapshot.

“Claude investigates through bounded read tools backed by that snapshot. The incident records tool activity, evidence references, the structured finding, the model used and usage. The agent does not silently substitute current configuration for historical evidence. Missing context requires abstention. Consumer expectations are labelled synthetic metadata; reviewed incident-memory retrieval is not yet implemented.

“In the complete target journey, a policy-controlled adapter applies an approved configuration correction using the expected revision. The producer emits new Kafka events with the repaired revision. Deterministic recovery checks require two fresh, non-overlapping passing windows before resolving the incident. PostgreSQL retains the evidence and decisions for later review.”

The last paragraph describes pending work until remediation and recovery are shipped. Remove future-tense qualifications only after a real deployed demonstration succeeds.

## Evidence upload

Produce a small PDF with a readable before/after panel and a results table. Preserve JSON/CSV exports, fixture definitions and the tested commit as supporting artifacts. Use synthetic inputs and do not include credentials.

The before/after panel should show the same incident: failing raw timestamps, producer revision and milliseconds contract before repair; the exact approved diff; then new records from the repaired revision and both passing recovery windows. Include timestamps, sample counts, incident/run IDs and actual model ID so screenshots can be traced to records.

Compare against a deterministic timestamp baseline that already recognizes likely unit mismatch. Use the same captured events and contracts. State that Sentinel additionally receives configuration history and consumer context; this is a system comparison, not an isolated claim of superior model intelligence.

Run the seven plan cases: seconds regression, microseconds regression, healthy traffic, delayed delivery, seconds allowed by contract, missing/conflicting context, and paused ingestion. Keep expected labels outside the agent inputs. Record violation classification, supported configuration attribution, consumer-context accuracy, proposed correction or abstention, and verified recovery. Also report fault-to-finding latency, token usage, failures and retry count. Do not count a retry as a new incident or a replay as another resolution.

A compact timestamp-only versus Sentinel comparison is sufficient for the first submission. A same-model context-ablation experiment is optional if time and credit remain. Do not invent accuracy percentages or human-hours-saved claims. Report the sample size and limitations of this controlled prototype.

## The single pitch slide

Use one visual hierarchy: headline at the top; one large product screenshot showing the incident, evidence-backed finding, repair diff and recovery; a compact architecture strip and measured proof underneath; a short customer/first-users line at the bottom. The slide must remain readable when projected, without depending on another slide or a separate video.

Suggested slide content:

- **Headline:** “Valid schema. Broken semantics. Verified recovery.”
- **Customer/problem:** Kafka platform teams investigating producer regressions that pass schema validation.
- **Journey:** Detect → investigate with captured evidence → approve exact change → verify fresh traffic.
- **Data strip:** Aiven Kafka → PostgreSQL incident evidence ↔ Claude tools → controlled producer → recovery proof.
- **Evidence:** Actual results from the seven cases, measured diagnosis/recovery timings and one before/after image. Fill numbers after evaluation.
- **Why now:** The product thesis is that typed agents can connect stream evidence and operational context, while approval and deterministic recovery keep consequential actions accountable. Present this as the team's thesis, not an unsupported market statistic.
- **First users:** Recruit a small design-partner group through direct outreach to Kafka/platform engineers and Aiven/Kafka communities. Start with a sandbox producer, review a recorded incident together, then pilot one additional contract against their real failure examples.

Show the actual model used in the product/run evidence. The pitch headline should emphasize the customer outcome rather than the model brand.

Publish the final slide with “Anyone with the link can view.” Verify the exact submitted link in a signed-out/private browser. The MP4, evidence upload and public slide are still deliverables to create; this document does not claim they exist.

## Delivery order

1. Redeploy and verify the current investigation-format/payload fix using the existing incident.
2. Implement exact proposals, approval, revision-checked execution and verified recovery.
3. Extend the existing workbench with exact proposals, approval decisions and recovery evidence; compact live activity and model metadata are implemented.
4. Verify the deployed journey and run the seven-case evaluation; save successes and failures.
5. Implement the planned isolated re-investigation, then record supporting proof without changing live configuration or resolution counts.
6. Rehearse and record the three-minute MP4; produce the evidence PDF and one pitch slide from measured results.
7. Check uploads, public slide access and a backup recording before the deadline.
