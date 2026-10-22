# Sentinel API collection

In Bruno, choose **Open Collection** and select this `bruno` directory. Select the **Local** or **Aiven** environment. Local uses `http://localhost:8080`; Aiven uses the Runtime URL already configured in this project.

The collection contains seventeen requests across three folders:

| Folder | Purpose |
|---|---|
| `01 Read-only` | Liveness, readiness, stream status, events, producer configuration/history, contracts, detection, incident lists and OpenAPI |
| `02 Incident evidence` | A recorded incident's signal/timeline and frozen evidence |
| `03 Producer controls` | Read the current revision, emit seconds/microseconds and restore milliseconds |

Run **01 Read-only** for an API smoke check. An empty incident list is valid. Warm-up and stale states remain visible in the response; HTTP 200 alone does not prove stream or contract health. HTTP 503 fails readiness assertions, and HTTP 404 on the new API routes means the target deployment does not contain those routes yet.

**List incidents** captures the newest `incident_id` as a runtime variable. Then open the detail and evidence requests. To select another incident, set `incident_id` in the selected environment. Leaving it blank uses the ID captured by the list request. Requests reject runtime IDs captured from another base URL.

For producer changes, set the **operator_token** secret in Bruno's selected environment to the same value as the application's `OPERATOR_TOKEN`. Only its secret-variable name is tracked in the collection; no token value is stored here. Database, Kafka and Anthropic credentials stay in the application environment and are not needed by Bruno.

Run **Read current configuration** before a producer change. It captures the producer revision in memory. Successful changes refresh that revision automatically. HTTP 409 means another change won the revision check; reread the configuration before retrying. Switching base URLs requires rereading the revision.

For a timestamp incident check:

1. Redeploy the latest application and allow about 70 seconds of healthy orders.
2. Check **Detection status** for a healthy baseline.
3. Read the current configuration, then send **Emit seconds** or **Emit microseconds**.
4. Wait 15–20 seconds and send **List incidents**.
5. Open **Incident detail** and **Frozen evidence**.
6. Send **Restore milliseconds**. New evaluations should become healthy; the existing incident and its evidence remain recorded.

Use one fault request at a time. Running all producer-control requests in sequence immediately restores milliseconds and does not leave the detector enough time to observe the fault.

If Bruno CLI is installed, run the read-only folder from the collection root:

```sh
cd bruno
bru run "01 Read-only" --env Local
bru run "01 Read-only" --env Aiven
```

The collection root also contains producer writes, so choose the folder matching the operation you intend. The `limit` environment variable defaults to 20; the API accepts 1–100.
