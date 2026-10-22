from uuid import UUID, uuid4

from psycopg import sql
from psycopg.types.json import Jsonb

from sentinel.investigation.settings import AGENT_VERSION, deadline_seconds
from sentinel.stream.postgres import PostgresRepository


class InvestigationConflict(ValueError):
    pass


class InvestigationRepository:
    def __init__(self, storage: PostgresRepository):
        self.storage = storage

    def enqueue(
        self, model_id: str, token_limit: int, topic: str, deadline: int | None = None
    ) -> None:
        with self.storage.connection() as connection:
            connection.execute(
                """
                INSERT INTO sentinel.investigations
                    (investigation_id, incident_id, snapshot_id, kind, status,
                     model_id, agent_version, token_limit, deadline_seconds)
                SELECT gen_random_uuid(), incident_id, snapshot_id, 'original',
                       'queued', %s, %s, %s, %s
                FROM sentinel.incidents i
                WHERE status = 'open' AND topic = %s AND NOT EXISTS (
                    SELECT 1 FROM sentinel.investigations r
                    WHERE r.incident_id = i.incident_id
                ) ON CONFLICT DO NOTHING
                """,
                (
                    model_id,
                    AGENT_VERSION,
                    token_limit,
                    deadline if deadline is not None else deadline_seconds(),
                    topic,
                ),
            )

    def claim(self) -> dict | None:
        with self.storage.connection() as connection:
            connection.execute(
                """
                UPDATE sentinel.investigations
                SET status = 'failed', error_code = 'interrupted', retryable = true,
                    finished_at = clock_timestamp()
                WHERE status = 'running'
                  AND started_at < clock_timestamp() - (deadline_seconds + 45) * interval '1 second'
                """
            )
            return connection.execute(
                """
                UPDATE sentinel.investigations SET status = 'running',
                    agent_version = %s, started_at = clock_timestamp()
                WHERE investigation_id = (
                    SELECT investigation_id FROM sentinel.investigations
                    WHERE status = 'queued' ORDER BY created_at
                    FOR UPDATE SKIP LOCKED LIMIT 1
                ) RETURNING *
                """,
                (AGENT_VERSION,),
            ).fetchone()

    def evidence(self, snapshot_id: UUID) -> dict:
        with self.storage.connection() as connection:
            return connection.execute(
                "SELECT body FROM sentinel.incident_snapshots WHERE snapshot_id = %s",
                (snapshot_id,),
            ).fetchone()["body"]

    def activity(
        self, investigation_id: UUID, call_id: str, tool: str, phase: str, body: dict
    ) -> None:
        with self.storage.connection() as connection:
            connection.execute(
                """
                INSERT INTO sentinel.investigation_activity
                    (activity_id, investigation_id, tool_call_id, tool_name, phase, body)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (uuid4(), investigation_id, call_id, tool, phase, Jsonb(body)),
            )

    def finish(
        self,
        investigation_id: UUID,
        finding: dict | None,
        usage: dict,
        duration_ms: int,
        error_code: str | None = None,
        error_detail: dict | None = None,
    ) -> None:
        with self.storage.connection() as connection:
            run = connection.execute(
                """
                UPDATE sentinel.investigations
                SET status = %s, finding = %s, usage = %s, duration_ms = %s,
                    error_code = %s, error_detail = %s, retryable = %s, finished_at = clock_timestamp()
                WHERE investigation_id = %s AND status = 'running' RETURNING incident_id
                """,
                (
                    "failed" if error_code else "completed",
                    Jsonb(finding),
                    Jsonb(usage),
                    duration_ms,
                    error_code,
                    Jsonb(error_detail),
                    error_code is not None,
                    investigation_id,
                ),
            ).fetchone()
            if run:
                connection.execute(
                    """
                    INSERT INTO sentinel.incident_timeline
                        (entry_id, incident_id, kind, recorded_at, body)
                    VALUES (%s, %s, %s, clock_timestamp(), %s)
                    """,
                    (
                        uuid4(),
                        run["incident_id"],
                        "investigation_failed"
                        if error_code
                        else "investigation_completed",
                        Jsonb(
                            {
                                "investigation_id": str(investigation_id),
                                "error_code": error_code,
                            }
                        ),
                    ),
                )

    def list(self, incident_id: UUID) -> list[dict]:
        with self.storage.connection() as connection:
            return connection.execute(
                """
                SELECT * FROM sentinel.investigations WHERE incident_id = %s
                ORDER BY created_at DESC LIMIT 100
                """,
                (incident_id,),
            ).fetchall()

    def detail(
        self, investigation_id: UUID, include_activity_bodies: bool = False
    ) -> dict | None:
        with self.storage.connection() as connection:
            run = connection.execute(
                "SELECT * FROM sentinel.investigations WHERE investigation_id = %s",
                (investigation_id,),
            ).fetchone()
            if run:
                run["activity"] = connection.execute(
                    sql.SQL("""
                    SELECT {} FROM sentinel.investigation_activity
                    WHERE investigation_id = %s ORDER BY recorded_at LIMIT 20
                    """).format(
                        sql.SQL(
                            "*"
                            if include_activity_bodies
                            else """
                        activity_id, investigation_id, tool_call_id, tool_name,
                        phase, recorded_at,
                        jsonb_array_length(body->'documents') AS document_count,
                        body->>'snapshot_id' AS snapshot_id,
                        body->>'status' AS result_status,
                        octet_length(body::text) AS body_bytes
                    """
                        )
                    ),
                    (investigation_id,),
                ).fetchall()
            return run

    def retry(
        self,
        incident_id: UUID,
        model_id: str,
        token_limit: int,
        deadline: int | None = None,
    ) -> dict | None:
        with self.storage.connection() as connection:
            incident = connection.execute(
                "SELECT * FROM sentinel.incidents WHERE incident_id = %s FOR UPDATE",
                (incident_id,),
            ).fetchone()
            if incident is None:
                return None
            previous = connection.execute(
                """
                SELECT status FROM sentinel.investigations WHERE incident_id = %s
                ORDER BY created_at DESC LIMIT 1
                """,
                (incident_id,),
            ).fetchone()
            if (
                incident["status"] != "open"
                or not previous
                or previous["status"] != "failed"
            ):
                raise InvestigationConflict()
            return connection.execute(
                """
                INSERT INTO sentinel.investigations
                    (investigation_id, incident_id, snapshot_id, kind, status,
                     model_id, agent_version, token_limit, deadline_seconds)
                VALUES (%s, %s, %s, 'retry', 'queued', %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    uuid4(),
                    incident_id,
                    incident["snapshot_id"],
                    model_id,
                    AGENT_VERSION,
                    token_limit,
                    deadline if deadline is not None else deadline_seconds(),
                ),
            ).fetchone()
