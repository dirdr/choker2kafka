from psycopg.types.json import Jsonb

from sentinel.producer.domain import CONFIG_PATH, SourceFile
from sentinel.stream.postgres import PostgresRepository


class ProducerRepository:
    def __init__(self, storage: PostgresRepository):
        self.storage = storage

    def apply(self, source: SourceFile) -> dict:
        config = source.configuration
        with self.storage.connection() as connection:
            current = connection.execute(
                "SELECT * FROM sentinel.producer_configurations WHERE producer_id = %s FOR UPDATE",
                (config.producer_id,),
            ).fetchone()
            previous = connection.execute(
                "SELECT * FROM sentinel.producer_sources WHERE producer_id = %s",
                (config.producer_id,),
            ).fetchone()
            changed = (
                previous is None
                or previous["file_sha"] != source.file_sha
                or current["event_time_unit"] != config.event_time_unit
            )
            if changed:
                row = connection.execute(
                    """
                    UPDATE sentinel.producer_configurations
                    SET revision = revision + 1, event_time_unit = %s, source_commit = %s,
                        updated_at = clock_timestamp()
                    WHERE producer_id = %s RETURNING *
                    """,
                    (
                        config.event_time_unit.value,
                        source.commit_sha,
                        config.producer_id,
                    ),
                ).fetchone()
                connection.execute(
                    """
                    INSERT INTO sentinel.producer_configuration_history
                        (producer_id, revision, event_time_unit, previous_unit, reason, actor, source_commit, source_file_sha)
                    VALUES (%s, %s, %s, %s, %s, 'git-sync', %s, %s)
                    """,
                    (
                        config.producer_id,
                        row["revision"],
                        config.event_time_unit.value,
                        current["event_time_unit"],
                        "Applied producer configuration file",
                        source.commit_sha,
                        source.file_sha,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO sentinel.producer_sources
                        (producer_id, repository, branch, file_path, file_sha, commit_sha, applied_revision, configuration)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (producer_id) DO UPDATE SET
                        repository = EXCLUDED.repository, branch = EXCLUDED.branch,
                        file_sha = EXCLUDED.file_sha, commit_sha = EXCLUDED.commit_sha,
                        applied_revision = EXCLUDED.applied_revision,
                        configuration = EXCLUDED.configuration, checked_at = clock_timestamp()
                    """,
                    (
                        config.producer_id,
                        source.repository,
                        source.branch,
                        CONFIG_PATH,
                        source.file_sha,
                        source.commit_sha,
                        row["revision"],
                        Jsonb(config.model_dump(mode="json")),
                    ),
                )
            else:
                connection.execute(
                    "UPDATE sentinel.producer_sources SET checked_at = clock_timestamp() WHERE producer_id = %s",
                    (config.producer_id,),
                )
        return {"changed": changed}

    def list(self) -> list[dict]:
        with self.storage.connection() as connection:
            return connection.execute(
                """
                SELECT c.producer_id, c.revision, c.event_time_unit, c.source_commit,
                       s.repository, s.branch, s.file_path, s.file_sha,
                       s.applied_revision, s.configuration, s.checked_at
                FROM sentinel.producer_configurations c
                LEFT JOIN sentinel.producer_sources s USING (producer_id)
                ORDER BY c.producer_id
                """
            ).fetchall()
