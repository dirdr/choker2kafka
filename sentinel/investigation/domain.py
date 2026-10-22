from typing import Literal

from pydantic import Field

from sentinel.detection.domain import FrozenModel


class Attribution(FrozenModel):
    producer_id: str
    configuration_revision: int = Field(gt=0)


class Finding(FrozenModel):
    conclusion: Literal["supported", "insufficient_evidence"]
    likely_cause: str = Field(min_length=1, max_length=1500)
    alternatives: list[str] = Field(min_length=1, max_length=5)
    affected_consumers: list[str] = Field(max_length=20)
    recommendation: str = Field(min_length=1, max_length=1500)
    confidence: Literal["low", "medium", "high"]
    confidence_rationale: str = Field(min_length=1, max_length=1500)
    evidence_ids: list[str] = Field(min_length=1, max_length=100)
    attribution: Attribution | None


class UnsupportedFinding(ValueError):
    pass


class CapturedEvidence:
    def __init__(self, snapshot_id: str, body: dict):
        self.snapshot_id = str(snapshot_id)
        self.body = body
        self.read_ids: set[str] = set()
        snapshot = body["snapshot"]
        self.events = snapshot["events"]
        self.producer_id = snapshot["producer_id"]
        self.documents = {
            "inspect_incident": [
                self.document(f"snapshot:{snapshot_id}", body["evaluation"]),
                *[
                    self.document(f"contract:{c['contract_id']}:{c['version']}", c)
                    for c in snapshot["contracts"]
                ],
                *[
                    self.document(f"event:{e['event_id']}", e)
                    for e in (*self.events[:5], *self.events[-5:])
                ],
            ],
            "lookup_producer_context": [
                *[
                    self.document(
                        f"configuration:{self.producer_id}:{c['revision']}", c
                    )
                    for c in body["producer_configuration_history"]
                ],
                *[
                    self.document(f"context:{c['producer_id']}:{c['version']}", c)
                    for c in body["producer_context_versions"]
                ],
            ],
        }

    @staticmethod
    def document(evidence_id: str, data: dict) -> dict:
        return {"evidence_id": evidence_id, "data": data}

    def read(self, tool: str) -> dict:
        if tool == "find_prior_incidents":
            return {
                "status": self.body.get("memory_capture_status", "unavailable"),
                "incidents": [],
                "detail": "Reviewed memory retrieval is not implemented; no cases supplied",
            }
        documents = self.documents[tool]
        self.read_ids.update(d["evidence_id"] for d in documents)
        return {
            "snapshot_id": self.snapshot_id,
            "documents": documents,
            "sample_selection": "First five and last five captured events; not the complete window",
            "missing_configuration_revisions": self.body.get(
                "missing_configuration_revisions", []
            ),
            "context_history_truncated": self.body.get(
                "context_history_truncated", False
            ),
        }

    def validate(self, finding: Finding) -> Finding:
        references = set(finding.evidence_ids)
        if not references <= self.read_ids:
            raise UnsupportedFinding("unknown_or_unread_evidence")
        consumers = {
            c["consumer_id"]
            for d in self.documents["lookup_producer_context"]
            if d["evidence_id"] in self.read_ids
            for c in d["data"].get("consumers", [])
        }
        if not set(finding.affected_consumers) <= consumers:
            raise UnsupportedFinding("unknown_consumer")
        if finding.conclusion == "insufficient_evidence":
            if finding.attribution is not None or finding.confidence == "high":
                raise UnsupportedFinding("unsupported_attribution")
            return finding
        attribution = finding.attribution
        if attribution is None or attribution.producer_id != self.producer_id:
            raise UnsupportedFinding("missing_producer_attribution")
        config_id = (
            f"configuration:{self.producer_id}:{attribution.configuration_revision}"
        )
        matching_events = {
            f"event:{e['event_id']}"
            for e in self.events
            if e["config_revision"] == attribution.configuration_revision
        }
        if (
            config_id not in references
            or not references.intersection(matching_events)
            or not any(r.startswith("contract:") for r in references)
            or self.body.get("context_history_truncated", False)
            or attribution.configuration_revision
            in self.body.get("missing_configuration_revisions", [])
        ):
            raise UnsupportedFinding("unsupported_configuration_attribution")
        return finding
