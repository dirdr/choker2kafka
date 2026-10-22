import json
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb
from pydantic import TypeAdapter

from sentinel.detection.domain import CheckResult, Contract, EventSample, WindowSnapshot
from sentinel.stream.postgres import PostgresRepository

MAX_EVENTS = 2000
MAX_CONTRACTS = 100
JSON_BODY = TypeAdapter(dict[str, Any])


class DetectionRepository:
    def __init__(self, storage: PostgresRepository):
        self.storage = storage

    def initialize(self, topic: str) -> None:
        self.storage.initialize()
        seed = json.loads(
            (Path(__file__).parent / "fixtures" / "orders.json").read_text()
        )
        contract = Contract.model_validate(seed["contract"])
        if topic != contract.topic:
            contract = contract.model_copy(
                update={"topic": topic, "contract_id": f"{topic}.checkout"}
            )
        context = seed["producer_context"]
        with self.storage.connection() as connection:
            connection.execute(
                "INSERT INTO sentinel.contract_versions "
                "(contract_id, version, topic, effective_from, definition) VALUES (%s, %s, %s, %s, %s) "
                "ON CONFLICT DO NOTHING",
                (
                    contract.contract_id,
                    contract.version,
                    topic,
                    contract.effective_from,
                    Jsonb(contract.model_dump(mode="json")),
                ),
            )
            connection.execute(
                "INSERT INTO sentinel.producer_context_versions "
                "(producer_id, version, effective_from, definition) VALUES (%s, %s, %s, %s) "
                "ON CONFLICT DO NOTHING",
                (
                    context["producer_id"],
                    context["version"],
                    context["effective_from"],
                    Jsonb(context),
                ),
            )
            connection.execute(
                "INSERT INTO sentinel.monitoring_runs (run_id, topic, producer_id) VALUES (%s, %s, 'checkout') "
                "ON CONFLICT (topic, producer_id) WHERE ended_at IS NULL DO NOTHING",
                (uuid4(), topic),
            )

    def evaluate_and_capture(
        self,
        topic: str,
        detector: Callable[[WindowSnapshot], list[CheckResult]],
        evaluated_at: datetime | None = None,
    ) -> list[CheckResult]:
        with self.storage.connection() as connection:
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            locked = connection.execute(
                "SELECT pg_try_advisory_xact_lock(hashtext(%s), hashtext('checkout')) AS acquired",
                (topic,),
            ).fetchone()
            if not locked["acquired"]:
                return []
            run = connection.execute(
                "SELECT * FROM sentinel.monitoring_runs "
                "WHERE topic = %s AND producer_id = 'checkout' AND ended_at IS NULL",
                (topic,),
            ).fetchone()
            if run is None:
                return []
            if evaluated_at is None:
                evaluated_at = connection.execute(
                    "SELECT date_bin(interval '5 seconds', clock_timestamp(), "
                    "TIMESTAMPTZ '2000-01-01') AS evaluated_at"
                ).fetchone()["evaluated_at"]
            snapshot = self.load_snapshot(connection, run, evaluated_at)
            results = detector(snapshot)
            for result in results:
                self.record(connection, snapshot, result)
            return results

    def load_snapshot(
        self, connection, run: dict, evaluated_at: datetime
    ) -> WindowSnapshot:
        start = max(run["started_at"], evaluated_at - timedelta(seconds=70))
        rows = connection.execute(
            "SELECT * FROM sentinel.events WHERE topic = %s AND producer_id = %s "
            "AND ingested_at >= %s AND ingested_at < %s ORDER BY ingested_at, event_id LIMIT %s",
            (run["topic"], run["producer_id"], start, evaluated_at, MAX_EVENTS + 1),
        ).fetchall()
        contracts = connection.execute(
            "SELECT definition FROM sentinel.contract_versions AS version "
            "WHERE topic = %s AND effective_from <= %s AND "
            "(effective_from >= %s OR effective_from = "
            "(SELECT max(effective_from) FROM sentinel.contract_versions AS previous "
            "WHERE previous.contract_id = version.contract_id AND previous.effective_from <= %s)) "
            "ORDER BY contract_id, effective_from LIMIT %s",
            (run["topic"], evaluated_at, start, start, MAX_CONTRACTS + 1),
        ).fetchall()
        latest = connection.execute(
            "SELECT greatest("
            "(SELECT max(ingested_at) FROM sentinel.events WHERE topic = %s AND producer_id = %s "
            "AND ingested_at >= %s AND ingested_at < %s), "
            "(SELECT max(ingested_at) FROM sentinel.rejected_records WHERE topic = %s "
            "AND ingested_at >= %s AND ingested_at < %s)) AS last_received_at",
            (
                run["topic"],
                run["producer_id"],
                run["started_at"],
                evaluated_at,
                run["topic"],
                run["started_at"],
                evaluated_at,
            ),
        ).fetchone()
        return WindowSnapshot(
            run_id=run["run_id"],
            run_started_at=run["started_at"],
            evaluated_at=evaluated_at,
            topic=run["topic"],
            producer_id=run["producer_id"],
            last_received_at=latest["last_received_at"],
            events=tuple(EventSample.model_validate(row) for row in rows[:MAX_EVENTS]),
            contracts=tuple(
                Contract.model_validate(row["definition"])
                for row in contracts[:MAX_CONTRACTS]
            ),
            overflow=len(rows) > MAX_EVENTS or len(contracts) > MAX_CONTRACTS,
        )

    def record(self, connection, snapshot: WindowSnapshot, result: CheckResult) -> None:
        inserted = connection.execute(
            "INSERT INTO sentinel.contract_evaluations "
            "(evaluation_id, run_id, topic, producer_id, contract_id, contract_version, rule_id, evaluated_at, status, result) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING RETURNING evaluation_id",
            (
                uuid4(),
                snapshot.run_id,
                snapshot.topic,
                snapshot.producer_id,
                result.contract_id,
                result.contract_version,
                result.rule_id,
                result.evaluated_at,
                result.status,
                Jsonb(result.model_dump(mode="json")),
            ),
        ).fetchone()
        if inserted is None or result.signal is None:
            return
        signal = result.signal
        fields = sorted(signal.affected_fields)
        active = connection.execute(
            "SELECT incident_id FROM sentinel.incidents WHERE run_id = %s AND topic = %s "
            "AND producer_id = %s AND contract_id = %s AND rule_id = %s AND affected_fields = %s "
            "AND configuration_revision IS NOT DISTINCT FROM %s AND status <> 'resolved'",
            (
                snapshot.run_id,
                snapshot.topic,
                snapshot.producer_id,
                signal.contract_id,
                signal.rule_id,
                fields,
                signal.configuration_revision,
            ),
        ).fetchone()
        if active:
            return
        snapshot_id, incident_id = uuid4(), uuid4()
        body = self.capture_context(connection, snapshot, result)
        connection.execute(
            "INSERT INTO sentinel.incident_snapshots (snapshot_id, captured_at, body) VALUES (%s, %s, %s)",
            (
                snapshot_id,
                snapshot.evaluated_at,
                Jsonb(JSON_BODY.dump_python(body, mode="json")),
            ),
        )
        connection.execute(
            "INSERT INTO sentinel.incidents "
            "(incident_id, run_id, topic, producer_id, rule_id, affected_fields, contract_id, contract_version, opened_at, snapshot_id, signal, configuration_revision) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                incident_id,
                snapshot.run_id,
                snapshot.topic,
                snapshot.producer_id,
                signal.rule_id,
                fields,
                signal.contract_id,
                signal.contract_version,
                snapshot.evaluated_at,
                snapshot_id,
                Jsonb(signal.model_dump(mode="json")),
                signal.configuration_revision,
            ),
        )
        connection.execute(
            "INSERT INTO sentinel.incident_timeline (entry_id, incident_id, kind, recorded_at, body) "
            "VALUES (%s, %s, 'detected', %s, %s)",
            (
                uuid4(),
                incident_id,
                snapshot.evaluated_at,
                Jsonb(
                    {
                        "snapshot_id": str(snapshot_id),
                        "signal_id": str(signal.signal_id),
                        "evaluation_id": str(inserted["evaluation_id"]),
                    }
                ),
            ),
        )

    def capture_context(
        self, connection, snapshot: WindowSnapshot, result: CheckResult
    ) -> dict:
        revisions = sorted({event.config_revision for event in snapshot.events})
        history = connection.execute(
            "SELECT * FROM sentinel.producer_configuration_history WHERE producer_id = %s "
            "AND changed_at <= %s AND (revision = ANY(%s) OR revision IN "
            "(SELECT revision FROM sentinel.producer_configuration_history WHERE producer_id = %s "
            "AND changed_at <= %s ORDER BY revision DESC LIMIT 100)) ORDER BY revision",
            (
                snapshot.producer_id,
                snapshot.evaluated_at,
                revisions,
                snapshot.producer_id,
                snapshot.evaluated_at,
            ),
        ).fetchall()
        contexts = connection.execute(
            "SELECT definition FROM sentinel.producer_context_versions WHERE producer_id = %s "
            "AND effective_from <= %s ORDER BY effective_from DESC LIMIT 101",
            (snapshot.producer_id, snapshot.evaluated_at),
        ).fetchall()
        return {
            "schema_version": 1,
            "snapshot": snapshot.model_dump(mode="json"),
            "evaluation": result.model_dump(mode="json"),
            "producer_configuration_history": history,
            "producer_configuration": history[-1] if history else None,
            "missing_configuration_revisions": sorted(
                set(revisions) - {row["revision"] for row in history}
            ),
            "producer_context_versions": [row["definition"] for row in contexts[:100]],
            "context_history_truncated": len(contexts) > 100,
            "eligible_prior_memory": [],
            "memory_capture_status": "not_implemented",
        }

    def contracts(self, topic: str, limit: int) -> list[dict]:
        with self.storage.connection() as connection:
            return connection.execute(
                "SELECT definition FROM sentinel.contract_versions WHERE topic = %s "
                "ORDER BY contract_id, effective_from DESC LIMIT %s",
                (topic, limit),
            ).fetchall()

    def status(self, topic: str) -> list[dict]:
        with self.storage.connection() as connection:
            return connection.execute(
                "SELECT DISTINCT ON (evaluation.contract_id, evaluation.rule_id) evaluation.run_id, evaluation.result "
                "FROM sentinel.contract_evaluations AS evaluation JOIN sentinel.monitoring_runs AS run "
                "ON run.run_id = evaluation.run_id WHERE evaluation.topic = %s AND run.ended_at IS NULL "
                "ORDER BY evaluation.contract_id, evaluation.rule_id, evaluation.evaluated_at DESC LIMIT 100",
                (topic,),
            ).fetchall()

    def incidents(self, limit: int, status: str | None = None) -> list[dict]:
        with self.storage.connection() as connection:
            return connection.execute(
                """
                SELECT i.incident_id, i.run_id, i.topic, i.producer_id, i.rule_id,
                       i.affected_fields, i.contract_id, i.contract_version,
                       i.status, i.opened_at, i.snapshot_id, i.configuration_revision,
                       i.signal->'observed'->'failure_ratio' AS failure_ratio,
                       r.status AS investigation_status,
                       r.model_id, r.finding->>'likely_cause' AS summary,
                       r.finding->>'conclusion' AS conclusion,
                       r.error_code
                FROM sentinel.incidents i
                LEFT JOIN LATERAL (
                    SELECT status, model_id, finding, error_code
                    FROM sentinel.investigations
                    WHERE incident_id = i.incident_id
                    ORDER BY created_at DESC, investigation_id DESC LIMIT 1
                ) r ON true
                WHERE (%s::text IS NULL OR i.status = %s)
                ORDER BY i.opened_at DESC, i.incident_id LIMIT %s
                """,
                (status, status, limit),
            ).fetchall()

    def incident(self, incident_id: UUID) -> dict | None:
        with self.storage.connection() as connection:
            incident = connection.execute(
                "SELECT * FROM sentinel.incidents WHERE incident_id = %s",
                (incident_id,),
            ).fetchone()
            if incident is None:
                return None
            incident["timeline"] = connection.execute(
                "SELECT * FROM sentinel.incident_timeline WHERE incident_id = %s "
                "ORDER BY recorded_at, entry_id LIMIT 100",
                (incident_id,),
            ).fetchall()
            return incident

    def evidence(self, incident_id: UUID) -> dict | None:
        with self.storage.connection() as connection:
            return connection.execute(
                "SELECT snapshot.snapshot_id, snapshot.captured_at, snapshot.body "
                "FROM sentinel.incident_snapshots AS snapshot JOIN sentinel.incidents AS incident "
                "ON incident.snapshot_id = snapshot.snapshot_id WHERE incident.incident_id = %s",
                (incident_id,),
            ).fetchone()
