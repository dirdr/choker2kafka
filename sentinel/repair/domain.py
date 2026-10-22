from dataclasses import dataclass

from sentinel.detection.domain import Contract, TimestampBounds
from sentinel.investigation.domain import Finding
from sentinel.producer.domain import ProducerFile


class RepairBlocked(ValueError):
    pass


@dataclass(frozen=True)
class Correction:
    producer_id: str
    revision: int
    before: ProducerFile
    after: ProducerFile
    file_sha: str
    commit_sha: str
    evidence_ids: list[str]


def correction(incident: dict, body: dict, finding: dict) -> Correction:
    result = Finding.model_validate(finding)
    if result.conclusion != "supported" or result.attribution is None:
        raise RepairBlocked("unsupported_finding")
    revision = incident["configuration_revision"]
    if (
        result.attribution.producer_id != incident["producer_id"]
        or result.attribution.configuration_revision != revision
    ):
        raise RepairBlocked("unsupported_revision")
    contract = next(
        (
            Contract.model_validate(item)
            for item in body["snapshot"]["contracts"]
            if item["contract_id"] == incident["contract_id"]
            and item["version"] == incident["contract_version"]
        ),
        None,
    )
    if contract is None:
        raise RepairBlocked("missing_contract")
    rule = next(
        (rule for rule in contract.rules if rule.rule_id == incident["rule_id"]), None
    )
    if (
        rule is None
        or rule.kind != "timestamp_bounds"
        or rule.fields != ("event_time",)
    ):
        raise RepairBlocked("unsupported_repair")
    expected = TimestampBounds.model_validate(rule.parameters).unit
    config = next(
        (
            item
            for item in body["producer_configuration_history"]
            if item["producer_id"] == incident["producer_id"]
            and item["revision"] == revision
        ),
        None,
    )
    if (
        not config
        or not config.get("source_file_sha")
        or not config.get("source_commit")
    ):
        raise RepairBlocked("configuration_not_git_managed")
    references = set(result.evidence_ids)
    if (
        f"configuration:{incident['producer_id']}:{revision}" not in references
        or f"contract:{contract.contract_id}:{contract.version}" not in references
    ):
        raise RepairBlocked("missing_evidence")
    if not any(
        f"event:{event['event_id']}" in references
        and event["config_revision"] == revision
        for event in body["snapshot"]["events"]
    ):
        raise RepairBlocked("missing_event_evidence")
    before = ProducerFile(
        producer_id=incident["producer_id"], event_time_unit=config["event_time_unit"]
    )
    after = before.model_copy(update={"event_time_unit": expected})
    if before == after:
        raise RepairBlocked("no_configuration_diff")
    return Correction(
        before.producer_id,
        revision,
        before,
        after,
        config["source_file_sha"],
        config["source_commit"],
        result.evidence_ids,
    )
