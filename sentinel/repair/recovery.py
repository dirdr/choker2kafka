from datetime import timedelta
from uuid import uuid4

from psycopg.types.json import Jsonb

from sentinel.detection.detectors import plausible
from sentinel.detection.domain import Contract, EventSample, TimestampBounds


def verify_recovery(storage, repair: dict, now=None) -> dict:
    proposal = repair["proposal"]
    with storage.connection() as connection:
        saved = connection.execute(
            "SELECT status FROM sentinel.repairs WHERE repair_id = %s FOR UPDATE",
            (repair["repair_id"],),
        ).fetchone()
        if saved is None or saved["status"] != "merged":
            return {"status": "waiting"}
        current = connection.execute(
            """
            SELECT c.*, s.file_sha, s.applied_revision
            FROM sentinel.producer_configurations c
            LEFT JOIN sentinel.producer_sources s USING (producer_id)
            WHERE c.producer_id = %s FOR UPDATE OF c
            """,
            (proposal["producer_id"],),
        ).fetchone()
        if (
            current["revision"] <= proposal["expected_revision"]
            or current["event_time_unit"] != proposal["after"]["event_time_unit"]
            or current["file_sha"] != repair["repair_file_sha"]
            or current["applied_revision"] != current["revision"]
        ):
            return {"status": "awaiting_source_sync"}
        incident = connection.execute(
            "SELECT * FROM sentinel.incidents WHERE incident_id = %s FOR UPDATE",
            (repair["incident_id"],),
        ).fetchone()
        active = connection.execute(
            "SELECT version, definition FROM sentinel.contract_versions WHERE contract_id = %s AND effective_from <= clock_timestamp() ORDER BY effective_from DESC LIMIT 1",
            (incident["contract_id"],),
        ).fetchone()
        if active is None or active["version"] != incident["contract_version"]:
            return {"status": "active_contract_changed"}
        contract = Contract.model_validate(active["definition"])
        rule = next(
            (item for item in contract.rules if item.rule_id == incident["rule_id"]),
            None,
        )
        if (
            rule is None
            or rule.kind != "timestamp_bounds"
            or rule.fields != ("event_time",)
        ):
            return {"status": "unsupported_recovery"}
        bounds = TimestampBounds.model_validate(rule.parameters)
        if now is None:
            now = connection.execute("SELECT clock_timestamp() AS now").fetchone()[
                "now"
            ]
        end = now.replace(microsecond=0, second=now.second - now.second % 10)
        start = end - timedelta(seconds=10)
        if start < current["updated_at"] or start < contract.effective_from:
            return {"status": "warming_up"}
        rows = connection.execute(
            "SELECT * FROM sentinel.events WHERE topic = %s AND producer_id = %s AND ingested_at >= %s AND ingested_at < %s ORDER BY ingested_at LIMIT 1001",
            (incident["topic"], incident["producer_id"], start, end),
        ).fetchall()
        latest = connection.execute(
            "SELECT max(ingested_at) AS at FROM sentinel.events WHERE topic = %s AND producer_id = %s",
            (incident["topic"], incident["producer_id"]),
        ).fetchone()["at"]
        rejected = connection.execute(
            "SELECT count(*) AS count FROM sentinel.rejected_records WHERE topic = %s AND ingested_at >= %s AND ingested_at < %s",
            (incident["topic"], start, end),
        ).fetchone()["count"]
        passing = sum(
            row["config_revision"] == current["revision"]
            and plausible(row["event_time"], EventSample.model_validate(row), bounds)
            for row in rows
        )
        fresh = latest is not None and timedelta(0) <= now - latest < timedelta(
            seconds=10
        )
        passed = (
            fresh and 50 <= len(rows) <= 1000 and passing == len(rows) and rejected == 0
        )
        evidence = {
            "samples": len(rows),
            "passing": passing,
            "rejected": rejected,
            "fresh": fresh,
            "event_ids": [str(row["event_id"]) for row in rows[:1000]],
            "contract_id": contract.contract_id,
            "contract_version": contract.version,
        }
        connection.execute(
            "INSERT INTO sentinel.recovery_windows (repair_id, configuration_revision, window_start, window_end, passed, evidence) VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
            (
                repair["repair_id"],
                current["revision"],
                start,
                end,
                passed,
                Jsonb(evidence),
            ),
        )
        windows = connection.execute(
            "SELECT * FROM sentinel.recovery_windows WHERE repair_id = %s ORDER BY window_end DESC LIMIT 2",
            (repair["repair_id"],),
        ).fetchall()
        verified = (
            len(windows) == 2
            and all(
                window["passed"]
                and window["configuration_revision"] == current["revision"]
                for window in windows
            )
            and windows[0]["window_end"] == end
            and windows[1]["window_end"] == start
        )
        connection.execute(
            "UPDATE sentinel.repairs SET recovery_revision = %s, status = %s, error_code = NULL, updated_at = clock_timestamp() WHERE repair_id = %s",
            (
                current["revision"],
                "verified" if verified else "merged",
                repair["repair_id"],
            ),
        )
        if verified and incident["status"] == "open":
            connection.execute(
                "UPDATE sentinel.incidents SET status = 'resolved', resolved_at = clock_timestamp() WHERE incident_id = %s",
                (incident["incident_id"],),
            )
            connection.execute(
                "INSERT INTO sentinel.incident_timeline (entry_id, incident_id, kind, recorded_at, body) VALUES (%s, %s, 'recovery_verified', clock_timestamp(), %s)",
                (
                    uuid4(),
                    incident["incident_id"],
                    Jsonb(
                        {
                            "repair_id": str(repair["repair_id"]),
                            "configuration_revision": current["revision"],
                            "windows": 2,
                            "pr_url": repair["pr_url"],
                        }
                    ),
                ),
            )
        return {
            "status": "verified" if verified else "checking",
            "passing_windows": sum(window["passed"] for window in windows),
        }
