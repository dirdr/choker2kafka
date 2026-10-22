from uuid import uuid4

from psycopg.types.json import Jsonb
from pydantic import ValidationError

from sentinel.github import GitHubClient
from sentinel.repair.domain import RepairBlocked, correction
from sentinel.stream.postgres import PostgresRepository


class RepairRepository:
    def __init__(self, storage: PostgresRepository):
        self.storage = storage

    def propose(self, client: GitHubClient) -> None:
        with self.storage.connection() as connection:
            candidates = connection.execute(
                """
                SELECT i.*, r.investigation_id, r.finding, s.body
                FROM sentinel.incidents i
                JOIN LATERAL (
                    SELECT investigation_id, finding FROM sentinel.investigations
                    WHERE incident_id = i.incident_id AND status = 'completed'
                    ORDER BY created_at DESC LIMIT 1
                ) r ON true
                JOIN sentinel.incident_snapshots s USING (snapshot_id)
                WHERE i.status = 'open'
                  AND r.finding->>'conclusion' = 'supported'
                  AND NOT EXISTS (SELECT 1 FROM sentinel.repairs p WHERE p.incident_id = i.incident_id)
                ORDER BY i.opened_at LIMIT 10
                """
            ).fetchall()
            for incident in candidates:
                repair_id = uuid4()
                status, error, proposal = "queued", None, {}
                try:
                    change = correction(incident, incident["body"], incident["finding"])
                    proposal = {
                        "producer_id": change.producer_id,
                        "contract_id": incident["contract_id"],
                        "contract_version": incident["contract_version"],
                        "expected_revision": change.revision,
                        "expected_file_sha": change.file_sha,
                        "source_commit": change.commit_sha,
                        "before": change.before.model_dump(mode="json"),
                        "after": change.after.model_dump(mode="json"),
                        "evidence_ids": change.evidence_ids,
                    }
                except RepairBlocked as blocked:
                    status, error = "blocked", str(blocked)
                except ValidationError:
                    status, error = "blocked", "invalid_stored_finding_or_contract"
                connection.execute(
                    """
                    INSERT INTO sentinel.repairs
                        (repair_id, incident_id, investigation_id, status, proposal, repository, base_branch, branch, error_code)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (incident_id) DO NOTHING
                    """,
                    (
                        repair_id,
                        incident["incident_id"],
                        incident["investigation_id"],
                        status,
                        Jsonb(proposal),
                        client.repository,
                        client.branch,
                        f"sentinel/repair-{repair_id.hex}",
                        error,
                    ),
                )

    def pending(self) -> list[dict]:
        with self.storage.connection() as connection:
            return connection.execute(
                "SELECT * FROM sentinel.repairs WHERE status IN ('queued', 'opening', 'error', 'open', 'merged') AND retry_at <= clock_timestamp() ORDER BY created_at LIMIT 10"
            ).fetchall()

    def current_revision(self, producer_id: str) -> int:
        with self.storage.connection() as connection:
            return connection.execute(
                "SELECT revision FROM sentinel.producer_configurations WHERE producer_id = %s",
                (producer_id,),
            ).fetchone()["revision"]

    def contract_is_current(self, proposal: dict) -> bool:
        with self.storage.connection() as connection:
            current = connection.execute(
                "SELECT version FROM sentinel.contract_versions WHERE contract_id = %s AND effective_from <= clock_timestamp() ORDER BY effective_from DESC LIMIT 1",
                (proposal["contract_id"],),
            ).fetchone()
        return (
            current is not None and current["version"] == proposal["contract_version"]
        )

    def update(
        self,
        repair: dict,
        status: str,
        error: str | None = None,
        pr: dict | None = None,
        merge_commit: str | None = None,
    ) -> None:
        with self.storage.connection() as connection:
            connection.execute(
                """
                UPDATE sentinel.repairs SET status = %s, error_code = %s,
                    pr_number = coalesce(%s, pr_number), pr_url = coalesce(%s, pr_url),
                    repair_file_sha = coalesce(%s, repair_file_sha),
                    merge_commit = coalesce(%s, merge_commit),
                    retry_at = clock_timestamp() + interval '10 seconds', updated_at = clock_timestamp()
                WHERE repair_id = %s
                """,
                (
                    status,
                    error,
                    (pr or {}).get("number"),
                    (pr or {}).get("html_url"),
                    (pr or {}).get("file_sha"),
                    merge_commit,
                    repair["repair_id"],
                ),
            )
            if status != repair["status"]:
                connection.execute(
                    "INSERT INTO sentinel.incident_timeline (entry_id, incident_id, kind, recorded_at, body) VALUES (%s, %s, %s, clock_timestamp(), %s)",
                    (
                        uuid4(),
                        repair["incident_id"],
                        f"repair_{status}",
                        Jsonb(
                            {
                                "repair_id": str(repair["repair_id"]),
                                "pr_url": (pr or {}).get("html_url")
                                or repair.get("pr_url"),
                                "error_code": error,
                            }
                        ),
                    ),
                )

    def detail(self, incident_id) -> dict | None:
        with self.storage.connection() as connection:
            repair = connection.execute(
                "SELECT * FROM sentinel.repairs WHERE incident_id = %s", (incident_id,)
            ).fetchone()
            if repair:
                repair["recovery_windows"] = connection.execute(
                    "SELECT * FROM sentinel.recovery_windows WHERE repair_id = %s ORDER BY window_end DESC LIMIT 2",
                    (repair["repair_id"],),
                ).fetchall()
            return repair
