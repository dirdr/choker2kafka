from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import ValidationError

from sentinel.connections import MissingConfiguration, required
from sentinel.stream.domain import (
    ConfigurationChange,
    OrderEvent,
    ProducerConfiguration,
    RevisionConflict,
    StreamRecord,
    transport_status,
)


class PostgresRepository:
    @contextmanager
    def connection(self):
        url = required("DATABASE_URL")
        sslmode = conninfo_to_dict(url).get("sslmode", "require")
        if sslmode not in {"require", "verify-ca", "verify-full"}:
            raise MissingConfiguration("DATABASE_URL must require TLS")
        with psycopg.connect(
            url,
            sslmode=sslmode,
            connect_timeout=5,
            options="-c statement_timeout=5000 -c lock_timeout=5000",
            row_factory=dict_row,
        ) as connection:
            yield connection

    def initialize(self) -> None:
        with self.connection() as connection:
            connection.execute("SELECT pg_advisory_xact_lock(782430091)")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS public.sentinel_migrations "
                "(name TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
            )
            for migration in sorted(
                (Path(__file__).parent / "migrations").glob("*.sql")
            ):
                applied = connection.execute(
                    "SELECT 1 FROM public.sentinel_migrations WHERE name = %s",
                    (migration.name,),
                ).fetchone()
                if applied:
                    continue
                connection.execute(migration.read_text())
                connection.execute(
                    "INSERT INTO public.sentinel_migrations (name) VALUES (%s)",
                    (migration.name,),
                )

    def configuration(self) -> ProducerConfiguration:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT producer_id, revision, event_time_unit "
                "FROM sentinel.producer_configurations WHERE producer_id = 'checkout'"
            ).fetchone()
        return ProducerConfiguration.model_validate(row)

    def change_configuration(
        self, change: ConfigurationChange
    ) -> ProducerConfiguration:
        with self.connection() as connection:
            previous = connection.execute(
                "SELECT event_time_unit FROM sentinel.producer_configurations "
                "WHERE producer_id = 'checkout' AND revision = %s FOR UPDATE",
                (change.expected_revision,),
            ).fetchone()
            if previous is None:
                raise RevisionConflict
            row = connection.execute(
                "UPDATE sentinel.producer_configurations "
                "SET revision = revision + 1, event_time_unit = %s, updated_at = clock_timestamp() "
                "WHERE producer_id = 'checkout' AND revision = %s "
                "RETURNING producer_id, revision, event_time_unit",
                (change.event_time_unit.value, change.expected_revision),
            ).fetchone()
            if row is None:
                raise RevisionConflict
            connection.execute(
                "INSERT INTO sentinel.producer_configuration_history "
                "(producer_id, revision, event_time_unit, previous_unit, reason, actor) "
                "VALUES (%s, %s, %s, %s, %s, 'operator')",
                (
                    row["producer_id"],
                    row["revision"],
                    row["event_time_unit"],
                    previous["event_time_unit"],
                    change.reason,
                ),
            )
        return ProducerConfiguration.model_validate(row)

    def configuration_history(self) -> list[dict]:
        with self.connection() as connection:
            return connection.execute(
                "SELECT * FROM sentinel.producer_configuration_history "
                "WHERE producer_id = 'checkout' ORDER BY revision DESC LIMIT 100"
            ).fetchall()

    def store(self, records: list[StreamRecord]) -> None:
        valid = []
        rejected = []
        for record in records:
            try:
                event = OrderEvent.model_validate_json(record.payload or b"")
            except ValidationError, ValueError:
                rejected.append(
                    (
                        record.topic,
                        record.partition,
                        record.offset,
                        record.kafka_timestamp_ms,
                        record.kafka_timestamp_type,
                        record.ingested_at,
                        record.payload,
                        "Invalid order event",
                    )
                )
                continue
            valid.append(
                (
                    event.event_id,
                    record.topic,
                    record.partition,
                    record.offset,
                    event.producer_id,
                    event.code_version,
                    event.config_revision,
                    event.event_time,
                    record.kafka_timestamp_ms,
                    record.kafka_timestamp_type,
                    record.ingested_at,
                    Jsonb(event.model_dump(mode="json")),
                )
            )
        with self.connection() as connection, connection.cursor() as cursor:
            if valid:
                cursor.executemany(
                    "INSERT INTO sentinel.events "
                    "(event_id, topic, partition, kafka_offset, producer_id, code_version, "
                    "config_revision, event_time, kafka_timestamp_ms, kafka_timestamp_type, ingested_at, payload) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                    valid,
                )
            if rejected:
                cursor.executemany(
                    "INSERT INTO sentinel.rejected_records "
                    "(topic, partition, kafka_offset, kafka_timestamp_ms, kafka_timestamp_type, ingested_at, payload, reason) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                    rejected,
                )

    def recent_events(self, limit: int) -> list[dict]:
        with self.connection() as connection:
            return connection.execute(
                "SELECT * FROM sentinel.events ORDER BY ingested_at DESC, event_id LIMIT %s",
                (limit,),
            ).fetchall()

    def status(self) -> dict:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT count(*) AS recent_events, max(ingested_at) AS last_ingested_at "
                "FROM sentinel.events WHERE ingested_at >= now() - interval '10 seconds'"
            ).fetchone()
            if row["last_ingested_at"] is None:
                latest = connection.execute(
                    "SELECT ingested_at FROM sentinel.events ORDER BY ingested_at DESC LIMIT 1"
                ).fetchone()
                row["last_ingested_at"] = latest["ingested_at"] if latest else None
        return {"transport": transport_status(row["last_ingested_at"]), **row}
