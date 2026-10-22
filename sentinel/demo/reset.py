import json
import os
from pathlib import Path

from psycopg.types.json import Jsonb

from sentinel.github import GitHubClient
from sentinel.producer.domain import CONFIG_PATH, SourceFile
from sentinel.stream.postgres import PostgresRepository


class DemoReset:
    def __init__(self, storage: PostgresRepository, stream):
        self.storage = storage
        self.stream = stream

    def applied(self, reset_id: str) -> bool:
        with self.storage.connection() as connection:
            return (
                connection.execute(
                    "SELECT 1 FROM sentinel.demo_resets WHERE reset_id = %s",
                    (reset_id,),
                ).fetchone()
                is not None
            )

    def run(self, reset_id: str) -> dict:
        if not reset_id or len(reset_id) > 100:
            raise ValueError("DEMO_RESET_ID must contain 1–100 characters")
        self.storage.initialize()
        if self.applied(reset_id):
            return {"status": "already_applied"}
        if os.getenv("GITHUB_TOKEN"):
            client = GitHubClient()
            commit = client.head()
            source = SourceFile.github(
                client.file(commit), commit, client.repository, client.branch
            )
        else:
            source = SourceFile.local(
                (Path(__file__).resolve().parents[2] / CONFIG_PATH).read_bytes()
            )
        fixture = json.loads(
            (
                Path(__file__).resolve().parents[1] / "detection/fixtures/orders.json"
            ).read_text()
        )
        expected = fixture["contract"]["rules"][0]["parameters"]["unit"]
        if source.configuration.event_time_unit.value != expected:
            raise ValueError(
                "Commit a healthy producer configuration before resetting the demo"
            )
        with self.storage.connection() as connection:
            active = connection.execute(
                "SELECT pr_number FROM sentinel.repairs WHERE pr_number IS NOT NULL AND status IN ('open', 'opening', 'error', 'stale')"
            ).fetchall()
        for repair in active:
            if not os.getenv("GITHUB_TOKEN"):
                raise ValueError("GitHub access is required to check active demo PRs")
            pr = client.request("GET", f"/pulls/{repair['pr_number']}")
            if pr["state"] == "open":
                raise ValueError(
                    "Close or merge active repair PRs before resetting the demo"
                )
        offsets = self.stream.watermarks()
        return self.clear(reset_id, offsets)

    def clear(self, reset_id: str, offsets: list[dict]) -> dict:
        with self.storage.connection() as connection:
            connection.execute("SELECT pg_advisory_xact_lock(782430091)")
            if connection.execute(
                "SELECT 1 FROM sentinel.demo_resets WHERE reset_id = %s", (reset_id,)
            ).fetchone():
                return {"status": "already_applied"}
            removed = connection.execute(
                "SELECT (SELECT count(*) FROM sentinel.incidents) AS incidents, (SELECT count(*) FROM sentinel.events) AS events, (SELECT count(*) FROM sentinel.investigations) AS investigations"
            ).fetchone()
            connection.execute("""
                TRUNCATE sentinel.recovery_windows, sentinel.repairs,
                    sentinel.investigation_activity, sentinel.investigations,
                    sentinel.incident_timeline, sentinel.incidents, sentinel.incident_snapshots,
                    sentinel.contract_evaluations, sentinel.monitoring_runs,
                    sentinel.events, sentinel.rejected_records,
                    sentinel.producer_sources, sentinel.producer_configuration_history,
                    sentinel.producer_configurations, sentinel.contract_versions,
                    sentinel.producer_context_versions, sentinel.ingestion_boundaries
                """)
            for offset in offsets:
                connection.execute(
                    "INSERT INTO sentinel.ingestion_boundaries (topic, partition, minimum_offset) VALUES (%s, %s, %s)",
                    (offset["topic"], offset["partition"], offset["offset"]),
                )
            connection.execute(
                "INSERT INTO sentinel.producer_configurations (producer_id, revision, event_time_unit) VALUES ('checkout', 1, 'milliseconds')"
            )
            connection.execute(
                "INSERT INTO sentinel.producer_configuration_history (producer_id, revision, event_time_unit, reason, actor) VALUES ('checkout', 1, 'milliseconds', 'Clean demo baseline', 'demo-reset')"
            )
            connection.execute(
                "INSERT INTO sentinel.demo_resets (reset_id, removed) VALUES (%s, %s)",
                (reset_id, Jsonb(removed)),
            )
        return {"status": "completed", "removed": removed}
