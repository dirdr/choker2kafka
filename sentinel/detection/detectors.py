from collections import Counter
from collections.abc import Callable
from datetime import timedelta
from statistics import median

from pydantic import ValidationError

from sentinel.detection.domain import (
    CheckResult,
    Contract,
    EventSample,
    Rule,
    Signal,
    TimestampBounds,
    WindowSnapshot,
    applicable_contract,
)
from sentinel.stream.domain import TimestampUnit

UNITS_PER_SECOND = {
    TimestampUnit.SECONDS: 1,
    TimestampUnit.MILLISECONDS: 1000,
    TimestampUnit.MICROSECONDS: 1_000_000,
}


def plausible(value: float, event: EventSample, bounds: TimestampBounds) -> bool:
    instant = event.ingested_at.timestamp() * UNITS_PER_SECOND[bounds.unit]
    return (
        instant - bounds.max_age_seconds * UNITS_PER_SECOND[bounds.unit]
        <= value
        <= instant + bounds.max_future_seconds * UNITS_PER_SECOND[bounds.unit]
    )


def timestamp_bounds(
    snapshot: WindowSnapshot, contract: Contract, rule: Rule
) -> CheckResult:
    base = {
        "contract_id": contract.contract_id,
        "contract_version": contract.version,
        "rule_id": rule.rule_id,
        "kind": rule.kind,
        "evaluated_at": snapshot.evaluated_at,
    }
    if snapshot.overflow:
        return CheckResult(**base, status="evidence_limit")
    latest = snapshot.last_received_at
    if (
        latest is not None and snapshot.evaluated_at - latest >= timedelta(seconds=10)
    ) or (
        latest is None
        and snapshot.evaluated_at - snapshot.run_started_at >= timedelta(seconds=10)
    ):
        return CheckResult(**base, status="stale")
    if rule.fields != ("event_time",):
        return CheckResult(**base, status="unsupported_rule")
    try:
        TimestampBounds.model_validate(rule.parameters)
        recent = []
        baseline = []
        for event in snapshot.events:
            if not snapshot.baseline_start <= event.ingested_at < snapshot.evaluated_at:
                continue
            if (
                event.topic != snapshot.topic
                or event.producer_id != snapshot.producer_id
            ):
                continue
            effective = applicable_contract(
                snapshot.contracts, contract.contract_id, event.ingested_at
            )
            effective_rule = (
                next(
                    (
                        candidate
                        for candidate in effective.rules
                        if candidate.rule_id == rule.rule_id
                    ),
                    None,
                )
                if effective
                else None
            )
            if (
                effective_rule is None
                or effective_rule.kind != rule.kind
                or effective_rule.fields != rule.fields
            ):
                return CheckResult(**base, status="missing_contract")
            bounds = TimestampBounds.model_validate(effective_rule.parameters)
            target = recent if event.ingested_at >= snapshot.recent_start else baseline
            target.append((event, bounds))
    except ValidationError:
        return CheckResult(**base, status="invalid_contract")
    counts = {"recent_samples": len(recent), "baseline_samples": len(baseline)}
    if len(recent) < 50 or len(baseline) < 100:
        return CheckResult(**base, **counts, status="warming_up")
    failures = [
        (event, bounds)
        for event, bounds in recent
        if not plausible(event.event_time, event, bounds)
    ]
    recent_median = median(event.event_time for event, _ in recent)
    baseline_median = median(event.event_time for event, _ in baseline)
    metrics = {
        "failure_ratio": len(failures) / len(recent),
        "baseline_failure_ratio": sum(
            not plausible(event.event_time, event, bounds) for event, bounds in baseline
        )
        / len(baseline),
        "recent_median": recent_median,
        "baseline_median": baseline_median,
        "median_scale_change": recent_median / baseline_median
        if baseline_median
        else None,
        "multiply_1000_plausible_ratio": sum(
            plausible(event.event_time * 1000, event, bounds)
            for event, bounds in failures
        )
        / len(failures)
        if failures
        else None,
        "divide_1000_plausible_ratio": sum(
            plausible(event.event_time / 1000, event, bounds)
            for event, bounds in failures
        )
        / len(failures)
        if failures
        else None,
        "contract_versions": sorted(
            {
                applicable_contract(
                    snapshot.contracts, contract.contract_id, event.ingested_at
                ).version
                for event, _ in recent
            }
        ),
    }
    if len(failures) * 5 <= len(recent) * 4:
        return CheckResult(**base, **counts, status="healthy", metrics=metrics)
    revision_samples = Counter(event.config_revision for event, _ in recent)
    revision_failures = Counter(event.config_revision for event, _ in failures)
    eligible = {
        revision
        for revision, count in revision_samples.items()
        if count >= 50 and revision_failures[revision] * 5 > count * 4
    }
    if not eligible:
        return CheckResult(
            **base,
            **counts,
            status="violated",
            metrics={**metrics, "capture_status": "revision_warming_up"},
        )
    triggering_event = max(
        (event for event, _ in failures if event.config_revision in eligible),
        key=lambda event: (event.ingested_at, str(event.event_id)),
    )
    triggering_contract = applicable_contract(
        snapshot.contracts, contract.contract_id, triggering_event.ingested_at
    )
    triggering_rule = next(
        candidate
        for candidate in triggering_contract.rules
        if candidate.rule_id == rule.rule_id
    )
    evidence = [f"event:{event.event_id}" for event, _ in failures]
    evidence.extend(
        f"contract:{contract.contract_id}:{version}"
        for version in metrics["contract_versions"]
    )
    signal = Signal(
        rule_id=rule.rule_id,
        kind=rule.kind,
        topic=snapshot.topic,
        producer_id=snapshot.producer_id,
        run_id=snapshot.run_id,
        affected_fields=rule.fields,
        configuration_revision=triggering_event.config_revision,
        contract_id=contract.contract_id,
        contract_version=triggering_contract.version,
        window_start=snapshot.recent_start,
        window_end=snapshot.evaluated_at,
        observed=metrics,
        expected={"parameters": triggering_rule.parameters, "violation_threshold": 0.8},
        evidence_ids=tuple(evidence),
    )
    return CheckResult(
        **base, **counts, status="violated", metrics=metrics, signal=signal
    )


Detector = Callable[[WindowSnapshot, Contract, Rule], CheckResult]
DETECTORS: dict[str, Detector] = {"timestamp_bounds": timestamp_bounds}


def evaluate(snapshot: WindowSnapshot) -> list[CheckResult]:
    results = []
    for contract_id in sorted(
        {contract.contract_id for contract in snapshot.contracts}
    ):
        contract = applicable_contract(
            snapshot.contracts, contract_id, snapshot.evaluated_at
        )
        if contract is None:
            continue
        for rule in contract.rules:
            detector = DETECTORS.get(rule.kind)
            if detector:
                results.append(detector(snapshot, contract, rule))
            else:
                results.append(
                    CheckResult(
                        contract_id=contract.contract_id,
                        contract_version=contract.version,
                        rule_id=rule.rule_id,
                        kind=rule.kind,
                        status="unsupported_rule",
                        evaluated_at=snapshot.evaluated_at,
                    )
                )
    return results
